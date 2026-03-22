# Assistant Operator Guide

This file is written for coding assistants and human maintainers who need to understand how to work safely in this repository.

## What This Repository Manages

This repository manages one Hetzner dedicated server that runs:

- Debian 13 as the base operating system
- Proxmox VE 9 as the hypervisor
- an internal guest network on `10.10.10.0/24`
- six managed VMs for ingress, Docker runtime, Docker builds, monitoring, PostgreSQL, and backups

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

The canonical identity classification and metadata contract lives in [docs/runbooks/identity-taxonomy-and-managed-principals.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/identity-taxonomy-and-managed-principals.md) and [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml).

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
5. Leave protected integration files alone unless you are doing the merge/integration step.
6. Merge to `main`, then bump `VERSION`.
7. Apply merged work live, then bump `platform_version` and refresh observed state.
8. Run `make preflight WORKFLOW=<id>` before long-running workflows that depend on controller-local secrets or external tokens.
9. Use `make workflows` or `make workflow-info WORKFLOW=<id>` when you need the canonical entry point instead of inferring it from prose.
10. Use `make commands` or `make command-info COMMAND=<id>` before mutating live systems so the approval policy, expected inputs, and rollback guidance are explicit.
11. After a real live apply, record the verification evidence in `receipts/live-applies/`.

At minimum, review whether these files need updates:

- [README.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/README.md)
- [workstreams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml)
- a workstream file in [docs/workstreams](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/workstreams)
- [VERSION](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/VERSION) only during integration to `main`
- [changelog.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/changelog.md) only during integration to `main`
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml) only for merged truth or verified live state
- a runbook in [docs/runbooks](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks)
- an ADR in [docs/adr](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr)
- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml) if an identity inventory, owner, scope boundary, or credential-storage contract changed

## Commands To Prefer

Use the [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) instead of rebuilding long commands from memory:

- `make start-workstream WORKSTREAM=adr-0011-monitoring`
- `make workflows`
- `make workflow-info WORKFLOW=converge-monitoring`
- `make commands`
- `make command-info COMMAND=configure-network`
- `make lanes`
- `make lane-info LANE=api`
- `make api-publication`
- `make api-publication-info SURFACE=proxmox-management-api`
- `make validate`
- `make validate-data-models`
- `make generate-status-docs`
- `make validate-generated-docs`
- `make receipts`
- `make preflight WORKFLOW=converge-monitoring`
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
- `make syntax-check-docker-runtime`
- `make converge-docker-runtime`
- `make converge-postgres-vm`
- `make syntax-check-uptime-kuma`
- `make syntax-check-open-webui`
- `make converge-open-webui`
- `make deploy-uptime-kuma`
- `make uptime-kuma-manage ACTION=list-monitors`
- `make database-dns`

## Things That Must Stay True

- repo and platform versioning remain separate
- ADRs record both decision state and implementation state
- branch workstream state lives in `workstreams.yaml` and `docs/workstreams/`
- protected integration files are changed only during merge/integration
- every named human, service, agent, and break-glass principal is classified in ADR 0046 terms before more automation is added
- shared values stay in inventory and group vars rather than copied into many tasks
- live one-off shell changes are either codified immediately or explicitly documented as temporary
- secrets and ephemeral provider passwords do not get committed
- workflow entry points stay declared in `config/workflow-catalog.json`
- mutating command contracts stay declared in `config/command-catalog.json`
- control-plane communication surfaces stay declared in `config/control-plane-lanes.json`
- API and webhook publication tiers stay declared in `config/api-publication.json`
- controller-local secret prerequisites stay declared in `config/controller-local-secrets.json`
- live applies keep structured evidence under `receipts/live-applies/`
- shared controller-side Python primitives stay centralized in `scripts/controller_automation_toolkit.py`
- `make validate` is the minimum repository gate before merge to `main`

## Pending Areas

These are the highest-value incomplete areas:

- guest-level exporter and alert expansion beyond the current Grafana plus Proxmox-metrics baseline
- live apply of ADR 0020 storage and backup automation
- guest subnet-route completion for ADR 0014 private guest access
- ADR 0024 Docker guest security baseline
- ADR 0025 compose-managed runtime stacks
