# AGENTS.md

## Purpose

This repository manages a dedicated Hetzner server that is intended to run Proxmox VE on top of Debian 13, with infrastructure changes tracked as code.

Both ChatGPT and Claude may be used in this repo. Work as if another assistant will continue after you.

## Working Rules

1. Leave the repo in a state where another assistant can continue without hidden context.
2. Record important decisions in `docs/adr/`.
3. Record operational procedures in `docs/runbooks/`.
4. Prefer committed automation over ad hoc shell changes on the server.
5. If a manual server change is unavoidable, document it immediately in the same turn.
6. Keep README status and next steps current when the server state materially changes.
7. Update `VERSION` and `versions/stack.yaml` whenever a change affects repository maturity, platform intent, or observed server state.
8. Update `changelog.md` whenever `VERSION` changes.
9. Keep everything DRY: centralize shared facts, avoid repeated shell snippets, and refactor duplication early.
10. Keep everything structurally solid: separate concerns, prefer small reversible changes, and do not mix bootstrap, security, storage, and Proxmox object management in one opaque step.
11. Every ADR must record both decision status and implementation state, including the first repo version, first platform version, and date where implementation became true.

## Current Infrastructure Context

- Provider: Hetzner dedicated server
- Hostname label: `proxmox_florin`
- Primary IPv4: `65.108.75.123`
- Base OS target: Debian 13
- Hypervisor target: Proxmox VE 9
- Desired management style: infrastructure as code

## Current Access State

As of 2026-03-21:

- Debian 13 is installed and reachable over SSH.
- routine host login now uses `ops` with `sudo`, not `root`.
- `root` remains key-only break-glass on the Proxmox host.
- Proxmox VE is installed from Debian packages.
- Observed kernel/banner: `Linux Debian-trixie-latest-amd64-base 6.17.13-2-pve`.
- Observed Proxmox manager version: `9.1.6`.
- `pveproxy` is listening on port `8006`.
- `vmbr0` now carries the public uplink and `vmbr10` provides the internal `10.10.10.0/24` guest network.
- Host-side IPv4 forwarding and NAT are enabled for guest egress.
- Public ingress on TCP `80/443` is forwarded to the NGINX VM at `10.10.10.10`.
- Template VM `9000` exists and the initial guest set (`110/120/130/140`) is provisioned and running.
- SSH password authentication is disabled on the host.
- Debian guests are intended to be managed as `ops` through the Proxmox jump path, not as `root`.
- `ops@pam` exists with `PVEAdmin` for routine Proxmox administration.
- The next risk area is management firewall policy, TFA, TLS, monitoring, notifications, and steady-state Tailscale access, not base VM creation.

Treat the next phase as ingress, security, backup, and API automation work.

## Expectations For Future Changes

When making meaningful infrastructure decisions, update:

- `README.md`
- `docs/adr/`
- `docs/runbooks/`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`

When adding automation later, prefer a structure like:

- `inventory/`
- `playbooks/`
- `roles/`
- `scripts/`

When implementing automation:

- put shared values in one place
- prefer reusable roles and templates over repeated ad hoc commands
- split responsibilities by concern
- remove duplication when it appears instead of documenting around it

Do not claim the platform is ready for routine production use until:

1. The running OS is confirmed to be the intended fresh Debian 13 install.
2. The bootstrap path is represented in version-controlled automation.
3. The Proxmox security baseline and access model are documented and applied.
4. Routine automation defaults to named non-root identities instead of `root`.
