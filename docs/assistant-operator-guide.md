# Assistant Operator Guide

This file is written for coding assistants and human maintainers who need to understand how to work safely in this repository.

## What This Repository Manages

This repository manages one Hetzner dedicated server that runs:

- Debian 13 as the base operating system
- Proxmox VE 9 as the hypervisor
- an internal guest network on `10.10.10.0/24`
- four initial VMs for ingress, Docker runtime, Docker builds, and monitoring

The repository is not only documentation. It is intended to be the operating contract for the live platform.

## Current Live Intent

The current target shape is:

- Proxmox host on public IPv4 `65.108.75.123`
- `vmbr0` for the public uplink
- `vmbr10` for the private guest network
- `10.10.10.10` NGINX
- `10.10.10.20` Docker runtime
- `10.10.10.30` Docker build
- `10.10.10.40` monitoring
- `lv3.org` as the public DNS zone

The authoritative machine-readable state is [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml).

## Default Operating Model

Use these defaults unless a runbook or break-glass situation explicitly requires otherwise:

- connect to the Proxmox host as `ops`
- use `sudo` for elevated Linux operations
- use `ops@pam` for routine Proxmox administration
- use `lv3-automation@pve` API tokens for non-human Proxmox object management
- treat `root` on the Proxmox host as break-glass only
- do not use `root` for guest SSH
- reach guests directly over the Tailscale-routed `10.10.10.0/24` path once ADR 0014 is applied
- if the tailnet path is unavailable, use the Proxmox host jump path only as break-glass

## What To Read Before Making Changes

1. [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
2. [AGENTS.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/AGENTS.md)
3. [docs/repository-map.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/repository-map.md)
4. [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
5. relevant ADRs in [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr)
6. relevant runbooks in [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks)

## How To Make A Safe Change

1. Identify or create the workstream before changing code.
2. Use one branch and preferably one worktree per workstream.
3. Change the automation first when feasible.
4. Update the workstream doc and registry while the work is in progress.
5. Merge to `main`, then bump `VERSION`.
6. Apply merged work live, then bump `platform_version` and refresh observed state.

At minimum, review whether these files need updates:

- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
- [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- a workstream file in [docs/workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams)
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION) when merging to `main`
- [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md) when `VERSION` changes
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- a runbook in [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks)
- an ADR in [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr)

## Commands To Prefer

Use the [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) instead of rebuilding long commands from memory:

- `make syntax-check`
- `make install-proxmox`
- `make configure-network`
- `make configure-ingress`
- `make configure-tailscale`
- `make provision-guests`
- `make harden-access`
- `make harden-guest-access`
- `make harden-security`
- `make provision-api-access`

## Things That Must Stay True

- repo and platform versioning remain separate
- ADRs record both decision state and implementation state
- branch workstream state lives in `workstreams.yaml` and `docs/workstreams/`
- shared values stay in inventory and group vars rather than copied into many tasks
- live one-off shell changes are either codified immediately or explicitly documented as temporary
- secrets and ephemeral provider passwords do not get committed

## Pending Areas

These are the highest-value incomplete areas:

- Tailscale private access rollout
- monitoring stack rollout
