# ADR 0154: VM-Scoped Parallel Execution Lanes

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.149.0
- Implemented In Platform Version: 0.131.0
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The platform already has enough orchestration to compile goals, reject semantic conflicts, and submit Windmill workflows, but its mutation path still degrades to "first workflow wins". A change to `netbox` and a change to `windmill` are independent at the service level, yet both land on `docker-runtime-lv3`; a change to `grafana` should not block a change to `netbox`, because those run on different VMs. Without an explicit per-VM concurrency model, multiple agents either collide on the same host or over-serialize unrelated work.

The practical isolation boundary on this platform is the VM:

- Proxmox schedules CPU and memory per guest.
- Ansible connects to each guest independently.
- Compose-managed services on one guest do not restart services on another guest.
- The Proxmox host and platform-wide control surfaces still need a bounded shared lane for host-only and cross-VM operations.

The platform needs a declared lane catalog, a lane resolver, a shared state registry that survives multiple local worktrees, and a queue/dispatcher pair that can defer work when a lane is saturated instead of rejecting it outright.

## Decision

We will treat the Proxmox host plus each managed VM as an **execution lane** with explicit capacity, and the scheduler will use that lane model before it submits mutation workflows.

The first production implementation lands in repo release `0.149.0` and platform version `0.131.0` with these concrete surfaces:

- [`config/execution-lanes.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/execution-lanes.yaml) declares the canonical lane catalog and per-lane slot count.
- [`platform/execution_lanes/catalog.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/execution_lanes/catalog.py) resolves an intent's primary lane and dependency lanes from the service catalog, dependency graph, and optional workflow lane overrides.
- [`platform/execution_lanes/registry.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/execution_lanes/registry.py) stores active lane leases and queued intents under the shared git common-dir so separate worktrees coordinate instead of diverging.
- [`platform/scheduler/scheduler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py) now queues mutation intents when a lane is saturated, dispatches queued work asynchronously, and records required lanes in scheduler metadata.
- [`platform/scheduler/watchdog.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/watchdog.py) releases lane leases and conflict claims when a queued job completes or violates a budget.
- [`config/windmill/scripts/lane-scheduler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/lane-scheduler.py) plus the seeded Windmill schedules provide the live dequeue loop.

### Lane catalog

The lane catalog is repo-managed and validated:

```yaml
schema_version: 1.0.0
lanes:
  lane:docker-runtime:
    hostname: docker-runtime-lv3
    vmid: 120
    services:
      - netbox
      - windmill
      - keycloak
      - openbao
    max_concurrent_ops: 3
    serialisation: resource_lock
```

Strict lanes (`serialisation: strict`) allow one operation per slot and are typically sized to `1`. Resource-lock lanes allow several concurrent operations on the same VM, but the existing conflict registry still blocks overlapping writes to the same service or secret.

### Required lane resolution

Compiled intents and direct workflow intents now carry `required_lanes`. Resolution uses three sources, in order:

1. the target service's VM in `config/service-capability-catalog.json`
2. the target host name in inventory-derived intent scope
3. optional workflow catalog lane overrides for host-wide or platform-wide flows

Dependency edges in `config/dependency-graph.json` contribute additional read-side lanes. If a mutation spans more than one primary VM lane, the resolver falls back to `lane:platform` as the primary serialising lane.

### Queueing and dispatch

If the primary lane has no free slots, the scheduler now writes an `intent.queued` ledger event and persists the request in the shared lane queue instead of returning a hard conflict. The repo-managed Windmill `lane_scheduler` script runs every two seconds, acquires newly free lane slots, and re-submits those queued intents to the scheduler in asynchronous mode.

The existing scheduler watchdog remains the authority for completion and cleanup. In this ADR it now releases:

- the active conflict claim for the intent
- the active lane lease for the intent
- the active-job state record used by budget monitoring

## Consequences

**Positive**

- Mutations on different VMs can progress in parallel without separate agents trampling the same guest.
- Multiple local worktrees now share the same execution-lane state because the lane registry uses the git common-dir, not a per-worktree temp file.
- Saturated lanes degrade to a queue instead of a failure, which is safer for operator-triggered or agent-triggered retries.

**Trade-offs**

- The first implementation still uses a repo-managed JSON registry rather than the future distributed lock backend proposed in later ADRs.
- Direct host-wide workflows that lack a target service or explicit lane override remain on the fallback path until their workflow metadata is tightened.
- Goal-compiler and CLI regression tests remain slower than the fast unit tests because health preconditions still wait on the existing maintenance-window best-effort tunnel timeout.

## Related ADRs

- ADR 0044: Windmill workflow runtime
- ADR 0075: Service capability catalog
- ADR 0112: Deterministic goal compiler
- ADR 0119: Budgeted workflow scheduler
- ADR 0127: Intent conflict resolution
