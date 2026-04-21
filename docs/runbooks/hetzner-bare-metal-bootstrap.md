# Runbook: Hetzner Bare-Metal Bootstrap for a Fork Clone

Target audience: an agent or operator standing up a new Hetzner dedicated
server as a fork-clone of this platform. Companion to ADR 0424.

**Base OS assumption**: Debian 13 (trixie). If Hetzner provisions a different
base OS, stop and update this runbook — do not guess.

---

## 0. Prerequisites (on workstation, before touching the box)

- The SSH private key matching the public key Hetzner has on file, at
  `.local/ssh/hetzner_llm_agents_ed25519` (key comment
  `llm-agents@proxmox_florin_server`).
- Hetzner DNS API token stored at `.local/hetzner/dns.env`:
  ```
  HETZNER_DNS_TOKEN=<token>
  HETZNER_DNS_ZONE=<zone, e.g. 0fork.com>
  ```
- The server's public IPv4, IPv6, and host-key fingerprint from the
  provisioning email.

### Verify, don't trust

```bash
# 1. Private key fingerprint matches the provisioning email's MD5
ssh-keygen -E md5 -lf .local/ssh/hetzner_llm_agents_ed25519

# 2. Host key fingerprint matches (mitigates MITM on first connect)
ssh-keyscan -t ed25519 -T 10 <IPv4> | ssh-keygen -lf -

# 3. DNS token actually works against the target zone
curl -s -H "Auth-API-Token: $(grep HETZNER_DNS_TOKEN .local/hetzner/dns.env | cut -d= -f2)" \
  https://dns.hetzner.com/api/v1/zones | python3 -c \
  "import json,sys; [print(z['name'], z['id']) for z in json.load(sys.stdin)['zones']]"
```

All three must pass. **If any do not, stop and escalate.**

---

## 1. Pin host key and probe system inventory

```bash
ssh-keyscan -t ed25519 -T 10 <IPv4> >> ~/.ssh/known_hosts
ssh -i .local/ssh/hetzner_llm_agents_ed25519 root@<IPv4> \
  'hostname; cat /etc/os-release | head -3; free -h | head -2; lsblk -d; ls /dev/kvm'
```

Record the output in the workstream YAML for this clone. If `/dev/kvm` is
missing on a nested-Proxmox target, stop — virt extensions are not enabled
(Hetzner AX41 has SVM by default; this should never fail, but verify).

---

## 2. Rename host

```bash
ssh ... root@<IPv4> 'hostnamectl set-hostname <new-hostname>'
```

Proposed convention: `fork-pve-01` for the first clone, increment for
subsequent. Update `/etc/hosts` accordingly (the Ansible role
`base_host_identity` handles this once Ansible is able to reach the box).

---

## 3. Disk layout — Hetzner default is ALREADY RAID1 (surprise)

**Critical**: Hetzner's default Debian 13 installimage builds `SWRAID 1`
across both NVMes without asking. The default layout is:

- `md0` (swap) mirrors `nvme0n1p1` ↔ `nvme1n1p1`
- `md1` (`/boot`) mirrors `nvme0n1p2` ↔ `nvme1n1p2`
- `md2` (`/`) mirrors `nvme0n1p3` ↔ `nvme1n1p3`

This means "skip RAID" is **not achievable post-provisioning** without a
rescue-mode reinstall. The only true no-RAID path is to boot the new server
into rescue mode, run `installimage` with `SWRAID 0`, and let it rewrite
the OS.

### Mandatory first check (before any partitioning!)

```bash
ssh root@<IPv4> 'lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS; echo; cat /proc/mdstat'
```

**Do NOT run `lsblk -d`** — the `-d` flag hides partitions and RAID members,
which on 2026-04-21 led an agent to conclude a mirror leg was "raw" and
attempt to repartition it. Recovery was possible only because
`partprobe` was not installed. See the ADR 0425 live postmortem for full
sequence.

### Consequence for this runbook

Accept the RAID1 the box came with. Do not attempt to reclaim either NVMe
as separate storage. PVE's default `local` directory storage at
`/var/lib/vz` uses `md2` and has ~443 GiB available — plenty for the
collapsed-topology VM plan.

If a fork operator genuinely needs no-RAID (e.g. to maximize usable space),
that is a pre-provisioning decision: order the server with rescue-mode access,
run `installimage SWRAID 0` manually before even booting into the installed
system.

---

## 4. Mesh VPN — Headscale, not external Tailscale

This platform runs its own Headscale instance as a platform service (see
prod `headscale.lv3.org`; clone target `headscale.0fork.com`). There is no
external Tailscale preauth key.

During bootstrap, operate over **public-IP SSH**. Once the clone's
Headscale service is deployed (part of the platform converge, after the
runtime-control VM is up), register the bare-metal host and the operator
workstation as Headscale clients using preauth keys issued by the clone's
own Headscale admin.

```bash
# LATER — after Headscale is deployed on the clone
# 1. On the Headscale server (inside a VM):
headscale preauthkeys create --user <operator> --reusable=false --expiration 1h

# 2. On the bare-metal host:
curl -fsSL https://tailscale.com/install.sh | sh   # tailscaled client works with headscale
tailscale up --login-server=https://headscale.0fork.com --authkey=<key> \
  --hostname=fork-pve-01 --ssh
```

Until that point, all SSH uses the public IP. This is fine for bootstrap;
the public IP is already firewalled by Hetzner's inbound ruleset and the
SSH key is ed25519-only.

---

## 5. Proxmox VE install (Proxmox-on-Debian, no rescue mode)

The existing [docs/runbooks/install-proxmox.md](install-proxmox.md) already
targets Debian 13 + PVE 9.1 and is a verified working path (last observed
2026-03-21 producing PVE 9.1.0 on kernel 6.17.13-2-pve). Run it against the
new box's inventory entry.

Manual fallback (the exact commands the playbook runs; useful if you're
driving by SSH rather than Ansible):

```bash
ssh root@<IPv4> <<'PVE'
# 1. Hostname + /etc/hosts (PVE refuses to install without FQDN resolving)
hostnamectl set-hostname <fork-pve-hostname>
sed -i '/^127\.0\.1\.1/d' /etc/hosts
echo "<ipv4> <hostname>.<domain> <hostname>" >> /etc/hosts

# 2. PVE repo + GPG key (trixie repo shipped 2026-04-20)
wget -qO /etc/apt/trusted.gpg.d/proxmox-release-trixie.gpg \
  https://enterprise.proxmox.com/debian/proxmox-release-trixie.gpg
echo "deb http://download.proxmox.com/debian/pve trixie pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-install-repo.list

# 3. Install PVE kernel
apt update
DEBIAN_FRONTEND=noninteractive apt install -y proxmox-default-kernel

# 4. Reboot into PVE kernel — RISK MOMENT
#    If the box doesn't come back, use Hetzner Robot KVM to select the
#    Debian kernel in grub (it's still installed as fallback).
reboot

# --- after reboot, re-SSH ---
# 5. Install proxmox-ve userland
DEBIAN_FRONTEND=noninteractive apt install -y proxmox-ve postfix open-iscsi chrony
apt remove -y linux-image-amd64 os-prober
pveversion
PVE
```

The `reboot` between steps 3 and 5 is the single riskiest moment of the
bootstrap. Before running it: verify `grep vmlinuz-.*-pve /boot/grub/grub.cfg`
shows the PVE kernel is present and listed first, and verify Hetzner Robot
access is working (you will need it if the reboot fails).

---

## 6. Identity overlay and first Ansible touch

On the workstation:

```bash
# 1. Create the overlay (do NOT commit)
cat > .local/identity.yml.<forkname> <<'YAML'
platform_domain: <fork-subdomain-or-apex>
platform_operator_email: operator@<fork-subdomain>
platform_operator_name: "<fork operator>"
hetzner_dns_zone_name: <actual-zone-at-hetzner>
management_ipv4: <new-ipv4>
management_gateway4: <new-ipv4-gateway>
management_ipv6: <new-ipv6>
management_interface: <iface-from-ip-brief-addr>
host_public_hostname: <new-hostname>
proxmox_node_name: <new-hostname>
YAML

# 2. Select it at runtime
export PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.<forkname>

# 3. Smoke-test Ansible connectivity
ansible -i inventory/hosts.yml <new-hostname> -m ping
```

---

## 7. rDNS (manual — no API)

Hetzner's **legacy** Robot API does not expose PTR record management for
dedicated servers. This must be done via the Robot UI:

1. Log into the Hetzner Robot (robot.hetzner.com).
2. Navigate to the server, "IPs" tab.
3. Set reverse DNS on the main IPv4 to `mail.<platform_domain>`.
4. Do the same for the primary IPv6.

Without this, outbound mail from the clone's Stalwart instance will be
rejected by most major mail providers (especially Gmail and Outlook).

---

## 8. Gate before continuing

Before running **any** `make converge-*` against the new box, verify:

- [ ] Tailscale-assigned IP resolves for the new hostname
- [ ] `ansible -m ping` succeeds from the workstation
- [ ] `.local/identity.yml.<forkname>` exists and is selected via env var
- [ ] `.local/hetzner/dns.env` token verified working against target zone
- [ ] rDNS set (if mail will be deployed)
- [ ] RAID1 built (if stateful VMs will live on this host)
- [ ] Operator has confirmed: subdomain vs apex, hostname, RAID decision

Any missing gate → stop, escalate to operator, do **not** proceed with
converges. The pattern "I'll just try it and see what breaks" is how `.local/`
got clobbered in ADR 0376.

---

## 9. First converge order (after all gates pass)

1. `make converge-proxmox-host env=clone`  — base PVE config
2. `make converge-proxmox-guests env=clone`  — create the 8 collapsed-topology VMs
3. `make converge-runtime-control env=clone`  — Keycloak, step-ca, OpenBao (identity anchor)
4. `make converge-postgres env=clone`  — shared DB
5. `make converge-mail-platform env=clone`  — Stalwart + Brevo bridge
6. `make converge-runtime-apps env=clone`  — application services
7. `make converge-monitoring env=clone`
8. `make converge-nginx-edge env=clone`  — last, once upstream services exist

Do **not** attempt step 9 (public DNS record publication) until nginx-edge
is healthy and presenting valid certs via step-ca.

---

## 10. Final validation before declaring the clone live

```bash
# Subdomain DNS resolves to the new server
dig +short A sso.<platform_domain>     # should be <new-ipv4>
dig +short AAAA sso.<platform_domain>  # should be <new-ipv6>

# Keycloak .well-known is reachable and signed by step-ca
curl -sS https://sso.<platform_domain>/realms/<realm>/.well-known/openid-configuration | jq .issuer

# Mail loop works: send a test message from the new operator address to a
# monitored external mailbox and verify SPF+DKIM+DMARC all pass in the headers.
```

If mail to external recipients lands in spam, check (in order):
1. rDNS set
2. SPF record includes Brevo's sending hosts
3. DKIM selector published on `clone.<domain>`
4. DMARC record present and aligned

These checks are implicit in the Stalwart role; the runbook lists them
here because every fork will get bit by at least one of them.
