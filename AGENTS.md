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
8. Keep everything DRY: centralize shared facts, avoid repeated shell snippets, and refactor duplication early.
9. Keep everything structurally solid: separate concerns, prefer small reversible changes, and do not mix bootstrap, security, storage, and Proxmox object management in one opaque step.

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
- `root` login works with the dedicated repo-local bootstrap key.
- Proxmox VE is installed from Debian packages.
- Observed kernel/banner: `Linux Debian-trixie-latest-amd64-base 6.17.13-2-pve`.
- Observed Proxmox manager version: `9.1.6`.
- `pveproxy` is listening on port `8006`.
- `vmbr0` now carries the public uplink and `vmbr10` provides the internal `10.10.10.0/24` guest network.
- Host-side IPv4 forwarding and NAT are enabled for guest egress.
- Template VM `9000` exists and the initial guest set (`110/120/130/140`) is provisioned and running.
- SSH to private guests through the Proxmox host works with the bootstrap key.
- The next risk area is ingress forwarding, firewall policy, and steady-state operator access, not base VM creation.

Treat the next phase as ingress, security, backup, and API automation work.

## Expectations For Future Changes

When making meaningful infrastructure decisions, update:

- `README.md`
- `docs/adr/`
- `docs/runbooks/`
- `VERSION`
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

Do not claim the server is ready for Proxmox installation until:

1. The running OS is confirmed to be the intended fresh Debian 13 install.
2. The bootstrap path is represented in version-controlled automation.
3. The Proxmox security baseline and access model are documented and applied.
