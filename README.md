# Proxmox Reference Platform

Forkable infrastructure-as-code reference for taking a Debian 13 host to a
repo-managed Proxmox VE platform.

This repository is being prepared for public GitHub publication. The committed
root surfaces now prefer generic language, repo-relative links, and portable
metadata so another team can clone, fork, and adapt the platform without first
rewriting one operator's workstation paths.

## What This Repo Includes

- architecture decisions in `docs/adr/`
- operational runbooks in `docs/runbooks/`
- parallel-workstream tracking from shard-backed sources under `workstreams/`,
  with `workstreams.yaml` preserved as a generated compatibility view
- automation and validation under `collections/`, `playbooks/`, `scripts/`,
  and `tests/`
- generated status and release surfaces that summarize current integrated
  repository truth

## Forking Guidance

1. Read `README.md`, `AGENTS.md`, `.repo-structure.yaml`,
   `.config-locations.yaml`, `docs/adr/.index.yaml`, and the shard-backed
   workstream registry surfaces under `workstreams/` (with `workstreams.yaml`
   as the generated compatibility view).
2. Replace deployment-specific inventory, hostnames, provider choices, and
   secrets with your own values before any live apply.
3. Keep personal machine paths, operator-specific credentials, and local
   bootstrap artefacts in ignored `.local/` state or environment variables.
4. Prefer repo-relative paths in committed metadata so worktrees, CI runners,
   and new forks all resolve the same contracts.

## Public Readiness

- public entrypoints are validated to reject committed workstation home paths
- workstream metadata now uses repository-relative docs and worktree paths
- release-note and status generators now emit repo-relative links
- the new ADR 0330-0339 bundle defines the remaining public-template and
  private-overlay work needed to keep the repo reproducible for forks

<!-- BEGIN GENERATED: platform-status -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Current Values
| Field | Value |
| --- | --- |
| Repository version | `0.178.18` |
| Platform version | `0.131.0` |
| Observed check date | `2026-04-03` |
| Observed OS | `Debian 13` |
| Observed Proxmox version | `9.1.6` |
| Observed kernel | `6.17.13-2-pve` |

### Topology Summary
| Field | Value |
| --- | --- |
| Managed guest count | 13 |
| Running guest count | 10 |
| Template VM present | `true` |
| Declared services | 72 |
| Publicly published services | 45 |

### Service Exposure Summary
| Exposure Model | Services |
| --- | --- |
| `edge-published` | 36 |
| `edge-static` | 1 |
| `informational-only` | 4 |
| `private-only` | 31 |

### Latest Live-Apply Evidence
| Capability | Receipt |
| --- | --- |
| `windmill` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `vaultwarden` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `uptime_kuma` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `temporal` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `step_ca` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `semaphore` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `openfga` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `openbao` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `nomad_scheduler` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `mailpit` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `mail_platform` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `keycloak` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `homepage` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `harbor` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `gitea` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `docker_runtime` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `api_gateway` | `2026-04-05-ws-0331-runtime-pool-mainline-live-apply` |
| `woodpecker` | `2026-04-04-ws-0335-service-recovery-followup-live-apply` |
| `searxng` | `2026-04-04-adr-0346-compose-dependency-health-gates-live-apply` |
| `runbook_task_reentry` | `2026-04-04-adr-0314-resumable-multi-step-flows-and-return-to-task-reentry-mainline-live-apply` |

Showing 20 of 171 capability receipts. Full history: [live-apply evidence history](docs/status/history/live-apply-evidence.md)
<!-- END GENERATED: platform-status -->

The current access posture is:

```text
ops SSH + sudo for routine host work
routine host SSH over the Proxmox Tailscale IP
ops@pam for routine Proxmox administration
lv3-automation@pve API token for durable Proxmox object management
short-lived `step-ca` SSH certificates accepted on the Proxmox host and managed guests
short-lived OpenBao AppRole artifacts refreshed on each converge and post-verification run
ops SSH + sudo for guest VMs
root key-only break-glass on the Proxmox host
root disabled for guest SSH
password SSH disabled on host and guests
```

## Control-plane lanes

<!-- BEGIN GENERATED: control-plane-lanes -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Lane Summary
| Lane | Title | Transport | Surfaces | Primary Rule |
| --- | --- | --- | --- | --- |
| `command` | Command Lane | `ssh` | 2 | Use SSH only for command-lane access. |
| `api` | API Lane | `https` | 16 | Default new APIs to internal-only or operator-only publication. |
| `message` | Message Lane | `authenticated_submission` | 2 | Submit platform mail through the internal mail platform rather than arbitrary external SMTP relays. |
| `event` | Event Lane | `mixed` | 16 | Event sinks must be documented and intentionally reachable. |

### API Publication Tiers
| Tier | Title | Surfaces | Summary |
| --- | --- | --- | --- |
| `internal-only` | Internal-Only | 20 | Reachable only from LV3 private networks, loopback paths, or explicitly trusted control-plane hosts. |
| `operator-only` | Operator-Only | 9 | Reachable only from approved operator devices over private access such as Tailscale. |
| `public-edge` | Public Edge | 3 | Intentionally published on a public domain through the named edge model. |
<!-- END GENERATED: control-plane-lanes -->


The generated lane summary above is the public-safe overview of the current control-plane model. Deeper deployment-specific operational details belong in runbooks, receipts, and fork-local overlays instead of the root README.

## Documents

<!-- BEGIN GENERATED: document-index -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

### Core Documents
- [Changelog](changelog.md)
- [Release notes](docs/release-notes/README.md)
- [Repository map](docs/repository-map.md)
- [Assistant operator guide](docs/assistant-operator-guide.md)
- [Release process](docs/release-process.md)
- [Workstreams registry](workstreams.yaml)
- [Workstreams guide](docs/workstreams/README.md)

### Discovery Indexes
- [ADR index](docs/adr/.index.yaml)
- [Runbooks directory](docs/runbooks)
- [Workstreams directory](docs/workstreams)
- [Release notes index](docs/release-notes/README.md)
- [Generated docs directory](docs/site-generated)
<!-- END GENERATED: document-index -->


## Versioning

- Repository version: [VERSION](VERSION)
- Desired platform and observed host state: [versions/stack.yaml](versions/stack.yaml)
- Versioning rules: [ADR 0008](docs/adr/0008-versioning-model-for-repo-and-host.md)
- Release notes index: [docs/release-notes/README.md](docs/release-notes/README.md)

Current values on `main`:

<!-- BEGIN GENERATED: version-summary -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

| Field | Value |
| --- | --- |
| Repository version | `0.178.18` |
| Platform version | `0.131.0` |
| Observed OS | `Debian 13` |
| Observed Proxmox installed | `true` |
| Observed PVE manager version | `9.1.6` |
| Declared services | 72 |
<!-- END GENERATED: version-summary -->

## Delivery Model

- ADRs remain the long-lived architecture truth
- active implementation is tracked in [workstreams.yaml](workstreams.yaml)
- each significant implementation stream gets a companion document under [docs/workstreams](docs/workstreams)
- branches and worktrees should stay easy to continue from another machine or fork
- version and release surfaces are reconciled on `main` during integration

## Merged Workstreams

<!-- BEGIN GENERATED: merged-workstreams -->
> Generated from canonical repository state by [`scripts/generate_status_docs.py`](scripts/generate_status_docs.py). Do not edit this block by hand.

Showing 25 of 299 merged or live-applied workstreams. Full history: [merged workstream history](docs/status/history/merged-workstreams.md)

| ADR | Title | Status | Doc |
| --- | --- | --- | --- |
| `0336` | Verify ADR 0336 public entrypoint leakage validation on the latest origin/main | `merged` | [ws-0336-live-apply.md](docs/workstreams/ws-0336-live-apply.md) |
| `0328` | Remove PatternFly v5 CSS from ops portal templates — eliminate layout collapse | `merged` | [0328-ops-portal.md](docs/adr/0328-ops-portal.md) |
| `0309` | Live apply task-oriented information architecture across the platform workbench from latest origin/main | `live_applied` | [ws-0309-live-apply.md](docs/workstreams/ws-0309-live-apply.md) |
| `0297` | Resolve Gitea release bundle retention and Renovate PR validation checkout drift | `live_applied` | [ws-0315-gitea-followups.md](docs/workstreams/ws-0315-gitea-followups.md) |
| `0295` | Live apply the shared artifact cache plane from latest origin/main | `live_applied` | [ws-0295-live-apply.md](docs/workstreams/ws-0295-live-apply.md) |
| `0293` | Integrate ADR 0293 exact-main LiveKit replay onto main | `merged` | [ws-0293-main-integration.md](docs/workstreams/ws-0293-main-integration.md) |
| `0259` | Integrate ADR 0259 exact-main replay onto current origin/main | `merged` | [ws-0259-main-merge.md](docs/workstreams/ws-0259-main-merge.md) |
| `0252` | Integrate ADR 0252 exact-main replay onto current origin/main | `merged` | [ws-0252-main-merge.md](docs/workstreams/ws-0252-main-merge.md) |
| `0238` | Integrate ADR 0238 operator grid into origin/main | `merged` | [ws-0238-main-integration.md](docs/workstreams/ws-0238-main-integration.md) |
| `0237` | Live apply schema-first human forms via React Hook Form and Zod | `live_applied` | [ws-0237-live-apply.md](docs/workstreams/ws-0237-live-apply.md) |
| `0236` | Live apply TanStack Query server-state conventions on the Windmill operator admin app | `live_applied` | [ws-0236-live-apply.md](docs/workstreams/ws-0236-live-apply.md) |
| `0232` | Integrate ADR 0232 live apply into origin/main | `merged` | [ws-0232-main-merge.md](docs/workstreams/ws-0232-main-merge.md) |
| `0206` | Integrate ADR 0206 live apply into origin/main | `merged` | [ws-0206-main-merge.md](docs/workstreams/ws-0206-main-merge.md) |
| `0181` | Off-host witness and control metadata replication | `live_applied` | [adr-0181-off-host-witness-replication.md](docs/workstreams/adr-0181-off-host-witness-replication.md) |
| `0179` | Service redundancy tier matrix | `merged` | [adr-0179-service-redundancy-tier-matrix.md](docs/workstreams/adr-0179-service-redundancy-tier-matrix.md) |
| `0178` | Dependency wave manifests for parallel apply | `merged` | [adr-0178-dependency-wave-manifests.md](docs/workstreams/adr-0178-dependency-wave-manifests.md) |
| `0176` | Inventory sharding and host-scoped Ansible execution | `live_applied` | [adr-0176-inventory-sharding.md](docs/workstreams/adr-0176-inventory-sharding.md) |
| `0173` | Workstream surface ownership manifest | `live_applied` | [adr-0173-workstream-surface-ownership-manifest.md](docs/workstreams/adr-0173-workstream-surface-ownership-manifest.md) |
| `0172` | Watchdog escalation and stale job self-healing | `merged` | [adr-0172-watchdog-escalation-and-stale-job-self-healing.md](docs/workstreams/adr-0172-watchdog-escalation-and-stale-job-self-healing.md) |
| `0171` | Controlled fault injection for resilience validation | `live_applied` | [adr-0171-controlled-fault-injection.md](docs/workstreams/adr-0171-controlled-fault-injection.md) |
| `0170` | Platform-wide timeout hierarchy | `live_applied` | [adr-0170-timeout-hierarchy.md](docs/workstreams/adr-0170-timeout-hierarchy.md) |
| `0169` | Structured log field contract | `live_applied` | [adr-0169-structured-log-field-contract.md](docs/workstreams/adr-0169-structured-log-field-contract.md) |
| `0168` | Ansible role idempotency CI enforcement | `merged` | [adr-0168-idempotency-ci.md](docs/workstreams/adr-0168-idempotency-ci.md) |
| `0167` | Graceful degradation mode declarations | `live_applied` | [adr-0167-graceful-degradation-mode-declarations.md](docs/workstreams/adr-0167-graceful-degradation-mode-declarations.md) |
| `0166` | Canonical error response format and error code registry | `live_applied` | [adr-0166-canonical-error-response-format.md](docs/workstreams/adr-0166-canonical-error-response-format.md) |
<!-- END GENERATED: merged-workstreams -->

## Next For Forks

1. Replace example deployment values with your own inventory, publication, and identity choices.
2. Keep operator-local overlays and secret material outside committed public entrypoints.
3. Run validation before the first live apply in a fresh environment.
