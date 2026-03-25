# ADR 0170: Platform-Wide Timeout Hierarchy

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: pending next main release
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-25

## Context

The platform already had several timeout-bearing layers, but they drifted independently:

- API gateway upstream requests used service-level literals in `config/api-gateway-catalog.json`.
- Windmill workflow budgets were tracked separately in `config/workflow-defaults.yaml` and `config/workflow-catalog.json`.
- SSH helper scripts such as `scripts/drift_lib.py` used literal `ConnectTimeout=` values.
- NetBox synchronization retried transient failures without an explicit total deadline.
- World-state workers mixed per-probe limits, subprocess limits, and implicit defaults.

That created two failure modes:

1. An outer operation can time out too early and cut off a legitimate inner request.
2. A lower layer can hang indefinitely because its own timeout budget is implicit or missing.

The platform already contains legitimate long-running workflows up to `7200` seconds and health probes up to `300` seconds, so the hierarchy has to validate real committed workloads instead of imposing an unrealistically small blanket cap.

## Decision

We will define a repository-managed timeout hierarchy in [`config/timeout-hierarchy.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/timeout-hierarchy.yaml) and use it as the canonical source for:

- maximum timeout ceilings per layer
- default timeout budgets when callers do not request an override
- validation of committed catalog values
- runtime timeout propagation in the critical live paths

### Canonical hierarchy

```yaml
layers:
  workflow_execution:
    timeout_s: 7200
    default_timeout_s: 600
    inner_layers: [ansible_play, api_call_chain, script_execution]

  ansible_play:
    timeout_s: 3600
    default_timeout_s: 480
    inner_layers: [ansible_task, ssh_connection]

  ansible_task:
    timeout_s: 600
    default_timeout_s: 120
    inner_layers: [ssh_connection, http_request, subprocess]

  ssh_connection:
    timeout_s: 120
    default_timeout_s: 30
    inner_layers: [subprocess]

  subprocess:
    timeout_s: 90
    default_timeout_s: 60
    inner_layers: []

  api_call_chain:
    timeout_s: 300
    default_timeout_s: 60
    inner_layers: [http_request]

  http_request:
    timeout_s: 60
    default_timeout_s: 30
    inner_layers: []

  script_execution:
    timeout_s: 900
    default_timeout_s: 300
    inner_layers: [http_request, subprocess]

  health_probe:
    timeout_s: 300
    default_timeout_s: 30
    inner_layers: [http_request]

  liveness_probe:
    timeout_s: 30
    default_timeout_s: 5
    inner_layers: []
```

Each parent layer must have a `timeout_s` strictly greater than the sum of its direct child `timeout_s` values. That rule is enforced by [`scripts/validate_timeout_hierarchy.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_timeout_hierarchy.py).

### Deadline propagation

Critical call paths use [`platform.timeouts.TimeoutContext`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/timeouts/context.py) to derive child timeouts from the remaining parent budget:

- API gateway webhook and upstream proxy requests
- NetBox synchronization retries
- world-state NetBox pagination and probe collection

That keeps each child operation bounded by both its layer ceiling and the remaining outer deadline.

### Runtime enforcement scope

The first implementation covers the current high-value paths:

- [`scripts/api_gateway/main.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/api_gateway/main.py)
- [`platform/scheduler/scheduler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py)
- [`platform/world_state/workers.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/world_state/workers.py)
- [`scripts/drift_lib.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/drift_lib.py)
- [`scripts/netbox_inventory_sync.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/netbox_inventory_sync.py)

The live scheduler watchdog seeding remains owned by ADR 0172. ADR 0170 depends on that path and aligns the timeout budgets used around it.

## Consequences

**Positive**

- Timeout ceilings and defaults now live in one file and are checked in repository validation.
- API gateway upstreams now converge on a 30-second request budget instead of mixed 15/20/30-second literals.
- NetBox sync, world-state probes, and SSH helper paths now have explicit bounded budgets derived from the same hierarchy.
- Scheduler-side Windmill API calls now use the same hierarchy as the gateway and workers.

**Negative / Trade-offs**

- The repository still contains timeout-bearing codepaths outside this first enforcement scope. This ADR governs the critical live paths first rather than forcing a repo-wide rewrite in one change.
- The hierarchy uses ceilings plus defaults rather than one fixed number for every workflow, because the live platform already has legitimate long-running workloads.

## Implementation Notes

- Repository validation now runs both [`scripts/validate_timeout_hierarchy.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_timeout_hierarchy.py) and [`scripts/check_hardcoded_timeouts.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/check_hardcoded_timeouts.py) through [`scripts/validate_repo.sh`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repo.sh).
- The API gateway runtime now bundles `config/timeout-hierarchy.yaml` into `/config/timeout-hierarchy.yaml` and exports `LV3_TIMEOUT_HIERARCHY_PATH` so the live container reads the same hierarchy as the repo.
- Windmill worker checkout already syncs the `windmill/` tree from ADR 0172; ADR 0170 reuses that live path rather than introducing a second watchdog entrypoint.

## Boundaries

- The hierarchy validates committed catalog values and governs the current critical live runtime paths. It does not yet rewrite every timeout in every script, Ansible verify snippet, or embedded service template in the repository.
- Workflow budgets in `config/workflow-catalog.json` remain the source of truth for per-workflow limits; ADR 0170 adds the outer ceiling and validation contract around them.

## Related ADRs

- ADR 0064: Health probe contracts for all services
- ADR 0092: Unified platform API gateway
- ADR 0113: World-state materializer
- ADR 0119: Budgeted workflow scheduler
- ADR 0163: Platform-wide retry taxonomy and exponential backoff
- ADR 0172: Watchdog escalation and stale job self-healing
