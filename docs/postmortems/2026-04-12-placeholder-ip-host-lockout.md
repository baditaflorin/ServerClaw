# Postmortem: Proxmox Host Total Lockout — Placeholder IP in /etc/network/interfaces

**Date:** 2026-04-12
**Severity:** CRITICAL (P0)
**Duration:** ~6 hours (approx. 03:00–09:00 UTC)
**Status:** Resolved
**Affected system:** Proxmox host `203.0.113.1` (all 14 VMs, all platform services)

---

## Summary

The Proxmox host became completely unreachable after `/etc/network/interfaces` was written with the RFC 5737 documentation placeholder IP `203.0.113.1/26` instead of the real IP `203.0.113.1/26`. When the network was reloaded (`ifreload -a`) during an Ansible convergence, `vmbr0` received the wrong IP. All inbound traffic to the real IP timed out at the network level — the server appeared offline. No application-level error was produced; the host was simply unreachable.

Recovery required Hetzner KVM console access and a rescue system boot. All 14 VMs remained running throughout but were inaccessible from the internet.

---

## Root Cause

**ADR 0407 (generic-by-default codebase)** replaced all real deployment values in git-tracked files with RFC 5737 placeholders (`203.0.113.x`, `192.0.2.x`) and `example.com`. The real values are injected at runtime from `.local/identity.yml` via `-e @.local/identity.yml`.

**What failed:** A convergence of `proxmox_network` (or equivalent) ran **without** the `.local/identity.yml` overlay being injected. The template `interfaces.j2` resolved `management_ipv4` to its default value — `203.0.113.1` — and wrote it to `/etc/network/interfaces`. On the next `ifreload -a` call, the bridge interface was reconfigured with the wrong IP.

**The placeholder was undetectable at write time.** The Ansible task succeeded with no warning. The file looked syntactically correct. The damage only became visible when the network was reloaded and the host's routable IP changed to a non-routable documentation address.

### Contributing factors

1. **No pre-write validation** — `proxmox_network` had no guard checking that `management_ipv4` was not a placeholder before writing `/etc/network/interfaces`
2. **Silent ifreload** — `ifreload -a` applies the wrong IP without connectivity checks or rollback
3. **No post-write connectivity probe** — Ansible `wait_for_connection` would detect the loss but only fires after `ifreload -a` completes, by which point the host may be unreachable
4. **pve-firewall lockout guard used wrong backend** — v0.178.122 added a guard checking `nft list ruleset` for ACCEPT rules after pve-firewall restart; but pve-firewall uses **iptables** (not nftables) for host INPUT policy, so the guard was checking the wrong chain and would have passed even if the host was locked out by iptables

---

## Timeline

| Time (UTC) | Event |
|-----------|-------|
| ~03:00 | Convergence runs `proxmox_network` without `.local/identity.yml`; `interfaces.j2` writes `203.0.113.1` to `/etc/network/interfaces` |
| ~03:00 | `ifreload -a` runs; `vmbr0` reconfigures to `203.0.113.1/26`; host immediately unreachable from internet |
| ~03:00 | All 14 VMs remain running but inaccessible |
| ~03:00–09:00 | Outage period; Tailscale and Gitea also unreachable (no route to host) |
| ~09:00 | Hetzner support ticket filed (#2026041203004207); KVM console access requested |
| ~09:30 | KVM credentials obtained; console attached |
| ~09:30 | Root cause identified: `ip addr show vmbr0` reveals `203.0.113.1/26` |
| ~09:35 | Immediate fix: `ip addr del 203.0.113.1/26 dev vmbr0 && ip addr add 203.0.113.1/26 dev vmbr0 broadcast 65.108.75.127`; routes restored |
| ~09:40 | `/etc/network/interfaces` corrected with real IP values |
| ~09:45 | SSH connectivity restored; all VMs reachable |
| ~10:00 | pve-firewall guard fixed (nftables → iptables); placeholder IP safety guard added |
| ~11:00 | v0.178.123 committed and pushed to GitHub main and private server |

---

## What We Fixed (v0.178.123)

### Fix 1 — Placeholder IP safety guard (`proxmox_network`)

Added an `ansible.builtin.assert` block **before any file is written** that aborts convergence if `management_ipv4` or `management_gateway4` matches RFC 5737 (203.0.113.x, 192.0.2.x, 198.51.100.x) or RFC 3849 (2001:db8::) placeholder ranges:

```yaml
- name: SAFETY GUARD — Reject RFC 5737 / placeholder management IP before writing host network config
  ansible.builtin.assert:
    that:
      - not (management_ipv4 | regex_search('^203\.0\.113\.'))
      - not (management_ipv4 | regex_search('^192\.0\.2\.'))
      - not (management_ipv4 | regex_search('^198\.51\.100\.'))
      - not (management_gateway4 | regex_search('^203\.0\.113\.'))
      - not (management_ipv4 | regex_search('^2001:db8:'))
    fail_msg: >-
      SAFETY GUARD TRIGGERED: management_ipv4={{ management_ipv4 }} is an RFC 5737/3849
      placeholder. Writing this to /etc/network/interfaces causes TOTAL HOST LOCKOUT.
      Fix: ensure .local/identity.yml is injected via -e @.local/identity.yml.
```

This guard fires before `template` or `copy` tasks run, producing a clear error and aborting convergence.

### Fix 2 — Correct pve-firewall lockout guard backend (`proxmox_security`)

Replaced the v0.178.122 nftables-based guard with an iptables-based guard targeting the correct chain:

```yaml
- name: Wait for pve-firewall to populate ACCEPT rules in PVEFW-HOST-IN (up to 30s)
  ansible.builtin.shell: |
    for i in $(seq 1 30); do
      if iptables -L PVEFW-HOST-IN -n 2>/dev/null | grep -qE '\bACCEPT\b'; then
        echo "OK"; exit 0
      fi
      sleep 1
    done
    echo "TIMEOUT"; exit 1
```

**Why nftables was wrong:** `pve-firewall` uses iptables (specifically `PVEFW-INPUT → PVEFW-HOST-IN`) for host INPUT policy. The `/etc/nftables.conf` managed by `proxmox_network` has `chain input { policy accept; }` — it explicitly accepts all and is not a lockout vector. Confirmed via `pve-firewall compile` output (iptables syntax) and live inspection during incident recovery.

### Fix 3 — `LV3_PROXMOX_HOST_PORT` env var support

Added `ansible_port: "{{ lookup('env', 'LV3_PROXMOX_HOST_PORT') | default(22, true) }}"` to the `proxmox-host` inventory entry, and `proxmox_guest_ssh_jump_port` to the ProxyJump args. This allows convergence to route through the break-glass SSH port (2222) when Tailscale is unavailable:

```bash
LV3_PROXMOX_HOST_ADDR=203.0.113.1 LV3_PROXMOX_HOST_PORT=2222 make converge-gitea env=production
```

### Fix 4 — `keycloak_local_artifact_dir` missing from `gitea.yml`

Added `keycloak_local_artifact_dir: "{{ repo_shared_local_root }}/keycloak"` to the play vars in `playbooks/gitea.yml` (was already in `keycloak.yml` but not inherited by `gitea.yml` which also invokes `keycloak_runtime`).

---

## Recovery Steps (for future reference)

If the Proxmox host is unreachable and you have KVM console access:

```bash
# 1. Log in via KVM console (root password or rescue system)

# 2. Identify the wrong IP
ip addr show vmbr0

# 3. Immediate connectivity fix (without reboot)
ip addr del 203.0.113.1/26 dev vmbr0
ip addr add 203.0.113.1/26 broadcast 65.108.75.127 dev vmbr0
ip route del default
ip route add default via 203.0.113.65 dev vmbr0

# 4. If SSH is not listening
systemctl start ssh

# 5. If pve-firewall is blocking
iptables -L PVEFW-HOST-IN -n   # check if ACCEPT rules are loaded
systemctl stop pve-firewall     # emergency: INPUT falls through to ACCEPT

# 6. Fix /etc/network/interfaces permanently (use real values)
# Real IP: 203.0.113.1/26, gateway: 203.0.113.65
# Edit: /etc/network/interfaces

# 7. Reload nftables (guest internet may be broken after recovery)
nft -f /etc/nftables.conf
```

If a rescue system is needed:
- Hetzner Robot → Server → Boot tab → Rescue system → activate
- Ticket for KVM: support.hetzner.com (allow 30–60 min for KVM credentials)
- In rescue: `mdadm --assemble --scan && mount /dev/md2 /mnt && mount /dev/md1 /mnt/boot && chroot /mnt`
- SSH key at `/etc/pve/priv/authorized_keys` — but this is a PVE cluster FS symlink; if PVE isn't running in rescue, create `/root/.ssh/authorized_keys` as a real file

---

## Lessons Learned

### For human operators

1. **Always inject `.local/identity.yml` before converging `proxmox_network` or `proxmox_host`**
   ```bash
   ansible-playbook ... -e @.local/identity.yml
   # The Makefile targets do this automatically — only skip if debugging
   ```

2. **The generic-by-default codebase (ADR 0407) is a two-edged sword.** It keeps the public repo clean, but every runtime variable that touches infrastructure must flow through `.local/identity.yml`. A convergence that "succeeds" without this file is silently wrong.

3. **Keep the break-glass SSH port (2222) permanently open in the Hetzner firewall.** Port 22 via Tailscale is the normal path, but Tailscale depends on the network being correct. If the network is wrong, Tailscale is also wrong.

4. **nftables `flush ruleset` at the top of `/etc/nftables.conf` is dangerous on boot.** If the nftables service loads before all bridge interfaces exist, the ruleset is applied to a partial network topology. After any host recovery, reload nftables manually: `nft -f /etc/nftables.conf`.

---

### For AI agents (Claude, future sessions, automated workflows)

This section exists specifically to teach AI agents how to prevent this class of incident.

#### Rule 1: Never run `proxmox_network` or `proxmox_host` without identity overlay

```
# FORBIDDEN — will write placeholder IPs to /etc/network/interfaces:
ansible-playbook playbooks/proxmox-host.yml -i inventory/hosts.yml

# REQUIRED — always inject identity:
ansible-playbook playbooks/proxmox-host.yml -i inventory/hosts.yml -e @.local/identity.yml
# OR use the Makefile which injects it automatically:
make converge-proxmox-host env=production
```

The safety guard (Fix 1 above) will now abort convergence if a placeholder slips through, but the best defence is prevention.

#### Rule 2: Confirm `management_ipv4` before writing network config

If you are writing any Ansible task that touches `/etc/network/interfaces`, `/etc/sysconfig/network-scripts/`, or any equivalent network config file on a production host:

1. Read `.local/identity.yml` first and verify `management_ipv4` is not a placeholder
2. Confirm it matches `ip addr show` on the live host before running any task that calls `ifreload`, `ifdown/ifup`, or `networkctl`
3. If you cannot verify, **do not run the task** — ask the operator to confirm

#### Rule 3: After any network change, probe connectivity before proceeding

After any task that modifies network configuration:
```yaml
- name: Verify host is still reachable after network change
  ansible.builtin.wait_for_connection:
    timeout: 30
    connect_timeout: 5
  # If this fails, the host is unreachable — abort and alert operator
```

The `proxmox_network` role already does this (the `Wait for SSH after network reload` task), but any ad-hoc modification must include the same check.

#### Rule 4: Understand pve-firewall's iptables backend

`pve-firewall` manages **iptables** chains (`PVEFW-INPUT`, `PVEFW-HOST-IN`, `PVEFW-FORWARD`), **not nftables**. The `/etc/nftables.conf` file is a separate system managing NAT/masquerade for guest internet egress and DNAT for inbound ports. They do not interact.

- To check if pve-firewall is active and has rules: `iptables -L PVEFW-HOST-IN -n`
- To check if guest internet works: `nft list ruleset | grep masquerade`
- If nftables is empty after recovery: `nft -f /etc/nftables.conf`

#### Rule 5: `LV3_PROXMOX_HOST_PORT=2222` is the recovery path when Tailscale is down

If `100.64.0.1:22` (Tailscale jump host) is unreachable, the break-glass path is:
```bash
LV3_PROXMOX_HOST_ADDR=203.0.113.1 LV3_PROXMOX_HOST_PORT=2222 make <target> env=production
```
This uses the public IP and the break-glass SSH port which is always open. Document this in your session notes whenever running playbooks while Tailscale is down.

#### Rule 6: OpenBao credential drift causes Gitea start failures

After credential rotation, OpenBao may serve stale secrets. Symptoms: `pq: password authentication failed for user "gitea"` in `docker logs gitea`. Fix: re-converge (`make converge-gitea env=production`) which will push the correct credentials from `.local/gitea/database-password.txt` to OpenBao and restart the container.

---

## Prevention Measures Implemented

| Layer | Measure | Status |
|-------|---------|--------|
| Pre-write validation | RFC 5737 assert guard in `proxmox_network` | ✅ Deployed in v0.178.123 |
| Wrong backend guard | iptables PVEFW-HOST-IN check in `proxmox_security` | ✅ Deployed in v0.178.123 |
| Break-glass routing | `LV3_PROXMOX_HOST_PORT` env var in inventory | ✅ Deployed in v0.178.123 |
| Gitea play fix | `keycloak_local_artifact_dir` in `gitea.yml` | ✅ Deployed in v0.178.123 |
| nftables reload | Manual procedure documented above | ✅ Documented |
| AI agent guidance | This postmortem's "For AI agents" section | ✅ This document |

## Remaining risks

| Risk | Mitigation needed |
|------|------------------|
| Other roles that write network config may not have placeholder guards | Audit all templates that write to `/etc/network*`, `/etc/sysconfig/network*` |
| nftables reload is manual after recovery | Consider adding a `nft -f /etc/nftables.conf` check to `proxmox_network` convergence |
| Hetzner KVM access can take 30–60 min | Pre-authorize KVM session token before any risky network operation |
| Tailscale dependency for normal SSH | Ensure break-glass port 2222 is always in Hetzner firewall allowlist |
