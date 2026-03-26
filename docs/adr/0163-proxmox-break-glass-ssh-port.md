# ADR 0163: Proxmox Break-Glass SSH Port

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.123.0
- Date: 2026-03-26

## Context

The Proxmox host firewall (`pve-firewall`) runs with `policy_in: DROP` and only allows
SSH from the management IPSET (`100.64.0.0/10` for Tailscale, `10.10.10.0/24` for the
internal guest bridge). This is correct security posture in normal operation.

The problem: both paths require a working Tailscale overlay. When Tailscale breaks —
most likely because the headscale coordination server loses its TLS certificate —
there is no route to the host that is inside the management IPSET. The only recovery
path then is the Hetzner rescue system, which takes 10+ minutes and requires
deactivating/reactivating a rescue image to boot into.

This failure mode has been observed when agent-driven playbook runs changed the
nginx edge configuration in a way that dropped the headscale TLS certificate from the
certbot domain list. Fixing a mis-configured cert should not require full rescue.

## Decision

Add a dedicated **break-glass SSH port** (`proxmox_breakglass_ssh_port`, default 2222)
that is openly reachable from the public internet via the Proxmox firewall.

Security properties:
- Password authentication is already globally disabled via `90-lv3-hardening.conf`
  (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`).
- Only the existing controller key (which is already the sole authorized key for the
  `ops` user) can authenticate. Exposing the port publicly is equivalent in risk to
  exposing any other SSH port that requires a specific key.
- The firewall rule is rendered deterministically from `proxmox_breakglass_ssh_port`
  in `cluster.fw.j2`, so it cannot be accidentally removed by a future playbook run.
- The sshd drop-in (`91-lv3-breakglass.conf`) explicitly declares `Port 22` alongside
  the break-glass port, ensuring port 22 is never lost even if the main sshd_config
  default changes.

## Consequences

- Agents and operators can SSH directly to `65.108.75.123:2222` without Tailscale.
- The `.ssh/config` `florin` entry (port 22, Tailscale IP) remains the preferred path;
  port 2222 is strictly a fallback.
- The Hetzner rescue system is now a last resort only for disk, bootloader, or
  kernel-level failures — not for firewall/certificate/network-layer lockouts.
- Future platform playbook runs are idempotent with respect to the break-glass port;
  they will render and apply it automatically.

## Implementation Notes

- `inventory/group_vars/all.yml`: added `proxmox_breakglass_ssh_port: 2222`.
- `proxmox_security/defaults/main.yml`: added `proxmox_breakglass_ssh_port: 2222`
  so any future Proxmox host in the inventory has the port by default.
- `proxmox_security/templates/cluster.fw.j2`: added
  `IN ACCEPT -p tcp -dport {{ proxmox_breakglass_ssh_port }} -comment break-glass`
  after the existing `proxmox_public_ingress_tcp_ports` block.
- `proxmox_security/tasks/main.yml`: added three tasks that render
  `/etc/ssh/sshd_config.d/91-lv3-breakglass.conf`, validate the full sshd
  config with `sshd -t`, and reload sshd — all conditional on
  `proxmox_breakglass_ssh_port` being defined and idempotent on re-run.
