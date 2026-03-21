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
7. Run parallel implementation through `workstreams.yaml` and `docs/workstreams/`, not through hidden chat context.
8. One chat thread should normally own one workstream, one branch, and preferably one git worktree.
9. Bump `VERSION` when work is merged to `main`, not for every branch-local change.
10. Bump `platform_version` in `versions/stack.yaml` only when merged work is actually applied live from `main`.
11. Update `changelog.md` whenever `VERSION` changes, and use the `Unreleased` section for merged notes that have not yet been cut into a numbered release.
12. When a live change is actually applied, finish the turn by committing it, pushing it to GitHub, and updating the relevant release/workstream state unless explicitly blocked.
13. Keep everything DRY: centralize shared facts, avoid repeated shell snippets, and refactor duplication early.
14. Keep everything structurally solid: separate concerns, prefer small reversible changes, and do not mix bootstrap, security, storage, and Proxmox object management in one opaque step.
15. Every ADR must record both decision status and implementation state, including the first repo version, first platform version, and date where implementation became true.

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
- `lv3-automation@pve` is the durable Proxmox API automation identity.
- Proxmox host firewall is enabled with SSH and `8006` restricted to declared management sources.
- A Let's Encrypt certificate is active for `proxmox.lv3.org`.
- Notifications are wired through a sendmail endpoint and a catch-all matcher.
- `ops@pam` has a TOTP factor configured.
- The next risk area is Tailscale, monitoring, and backup policy, not base VM creation.

Treat the next phase as ingress, security, backup, and API automation work.

## Expectations For Future Changes

When making meaningful infrastructure decisions, update:

- `README.md`
- `docs/adr/`
- `docs/runbooks/`
- `docs/workstreams/` when the change is part of an active workstream
- `workstreams.yaml`
- `VERSION` when merging to `main`
- `changelog.md` when `VERSION` changes
- `versions/stack.yaml`
- a Git push if the change was applied live

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
