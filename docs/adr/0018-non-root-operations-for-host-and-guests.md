# ADR 0018: Non-Root Operations For Host And Guests

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.10.0
- Implemented In Platform Version: 0.8.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The platform already has a working bootstrap SSH key, but routine operations were still easy to perform as `root`, especially on the Proxmox host. That keeps the attack surface and the blast radius too high for normal engineering work.

The intended operating model is:

- named non-root operator access for the Proxmox host
- named non-root operator access for guest VMs
- `sudo` for controlled privilege escalation
- `root` retained only for break-glass recovery

## Decision

We will make `ops` the default interactive and automation identity for both the Proxmox host and Debian guests.

On the Proxmox host:

1. use `ops` for SSH and Ansible by default
2. keep `root` as key-only break-glass SSH
3. keep `ops@pam` for routine Proxmox administration

On Debian guests:

1. use `ops` for SSH and Ansible by default
2. disable SSH password authentication
3. disable direct root SSH
4. reach private guests through the Proxmox host jump path until Tailscale is in place

## Consequences

- Routine work no longer requires direct root sessions from operator laptops.
- Audit trails become clearer because the steady-state identity is named and consistent.
- Existing automation must target `ops` plus `sudo`, not `root`.
- Break-glass recovery still exists, but it is no longer the normal path.

## Sources

- <https://pve.proxmox.com/pve-docs/chapter-pveum.html>
- <https://pve.proxmox.com/mediawiki/index.php?title=Proxmox_VE_API>
