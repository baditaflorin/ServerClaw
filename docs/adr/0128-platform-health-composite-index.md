# ADR 0128: Platform Health Composite Index

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.125.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

Platform health signals already exist, but they are spread across multiple sources:

- world-state service health from ADR 0113
- SLO error budgets from ADR 0096
- drift receipts from ADR 0091
- active maintenance windows from ADR 0080
- open incident triage reports from ADR 0114
- mutation intent state from ADR 0115

That fragmentation makes every caller reimplement its own health judgement. The platform API, CLI, goal compiler, and future automation gates should not all decide independently whether a service is safe to mutate.

## Decision

We will maintain a per-service composite health index backed by Postgres and refreshed from a Windmill workflow every minute.

Each entry stores:

- `composite_status`: `healthy`, `degraded`, `critical`, or `maintenance`
- `composite_score`: `0.0` to `1.0`
- `safe_to_act`: gate-friendly boolean
- `computed_at` and `ttl_seconds`
- the contributing signal set with score, weight, and human-readable reason

The current weighted signals are:

| Signal | Weight |
| --- | --- |
| `health_probe` | `0.40` |
| `slo_budget` | `0.20` |
| `drift_free` | `0.15` |
| `open_incidents` | `0.15` |
| `pending_mutations` | `0.10` |

Special handling applies for:

- active maintenance windows: force `maintenance` at `0.90`
- exhausted SLO budget: force `critical` at `0.00`
- failing health probe plus an open incident: force `critical` at `0.00`

The index is exposed through:

- `platform.health.HealthCompositeClient`
- `GET /v1/platform/health`
- `GET /v1/platform/health/{service_id}`
- `lv3 health`

The goal compiler now checks the composite index before compiling service mutations. Unsafe health fails compilation with `HEALTH_UNSAFE` unless the caller explicitly uses `--force-unsafe-health`, which is recorded in the ledger metadata.

## Consequences

Positive:

- one scoring contract now serves the API, CLI, and mutation gate
- the signal list makes unsafe decisions explainable instead of opaque
- a scheduled Windmill refresh keeps the index cheap to query and easy to cache

Negative:

- signal weights are repository-managed and opinionated
- composite freshness now depends on the refresh cadence and storage path
- the platform still needs a live apply from `main` before the Windmill schedule and Postgres schema become active in production

## Boundaries

- the index is read-only aggregation; it does not remediate anything
- `safe_to_act` is a hard gate for goal-compiled mutations, not for read-only diagnostics
- this ADR does not replace ADR 0127-style conflict detection; it only contributes mutation-state awareness to the health score

## Related ADRs

- ADR 0064: Health probe contracts
- ADR 0080: Maintenance window and change suppression protocol
- ADR 0091: Continuous drift detection
- ADR 0092: Unified platform API gateway
- ADR 0096: SLO tracking
- ADR 0113: World-state materializer
- ADR 0114: Rule-based incident triage engine
- ADR 0115: Event-sourced mutation ledger
- ADR 0123: Service uptime contracts and monitor-backed health
