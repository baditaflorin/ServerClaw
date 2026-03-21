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
- treat `root` on the Proxmox host as break-glass only
- do not use `root` for guest SSH
- reach guests through the Proxmox jump path until Tailscale exists

## What To Read Before Making Changes

1. [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
2. [AGENTS.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/AGENTS.md)
3. [docs/repository-map.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/repository-map.md)
4. relevant ADRs in [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr)
5. relevant runbooks in [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks)

## How To Make A Safe Change

1. Identify the architectural source of truth.
2. Change the automation first when feasible.
3. Apply and verify the change.
4. Record the result in the repository in the same turn.
5. If the change was applied live, bump the repo version and push the commit in the same turn unless blocked.

At minimum, review whether these files need updates:

- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION)
- [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md)
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
- a runbook in [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks)
- an ADR in [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr)

## Commands To Prefer

Use the [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) instead of rebuilding long commands from memory:

- `make syntax-check`
- `make install-proxmox`
- `make configure-network`
- `make configure-ingress`
- `make provision-guests`
- `make harden-access`
- `make harden-guest-access`
- `make harden-security`

## Things That Must Stay True

- repo and platform versioning remain separate
- ADRs record both decision state and implementation state
- shared values stay in inventory and group vars rather than copied into many tasks
- live one-off shell changes are either codified immediately or explicitly documented as temporary
- secrets and ephemeral provider passwords do not get committed

## Pending Areas

These are the highest-value incomplete areas:

- Tailscale private access rollout
- monitoring stack rollout
- API-token-based automation identity
