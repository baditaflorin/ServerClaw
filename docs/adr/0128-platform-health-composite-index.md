# ADR 0128: Platform Health Composite Index

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Platform health information currently lives in multiple sources that any agent or operator must query and synthesise independently:

- **Health probe status**: per-service HTTP/TCP/command results (ADR 0064), refreshed every 30 seconds in the world-state materializer (ADR 0113).
- **SLO error budget**: per-service budget consumption (ADR 0096), computed from Prometheus.
- **Drift findings**: per-surface drift flags from the continuous drift detector (ADR 0091).
- **Open incidents**: active triage runs from the closure loop (ADR 0126) and GlitchTip (ADR 0061).
- **Maintenance windows**: active suppression windows (ADR 0080).
- **Pending intents**: intents in `pending_approval` or `executing` states in the ledger (ADR 0115).
- **Observation findings**: severity-flagged findings from the last observation loop run (ADR 0071).

When an agent (or a human) wants to answer "is it safe to deploy to netbox right now?", they must query all of these sources, apply their own weighting, and reach a conclusion. This is:

- **Inconsistent**: different agents weigh the same signals differently and may reach different conclusions for the same state.
- **Slow**: assembling a health picture from 7 sources costs multiple round trips per request.
- **Invisible**: the components that need a "safe to proceed" answer (goal compiler, closure loop, triage engine) each implement their own ad hoc version of this check.

A single, continuously-updated **health composite index** per service reduces all of these signals to one queryable score per service with an explicit safe/degraded/critical classification and a human-readable reason string.

## Decision

We will implement a **platform health composite index** as a materialised table in Postgres, updated by a Windmill workflow that runs every 60 seconds and aggregates all health signals into a per-service health entry.

### Health entry structure

```python
@dataclass
class ServiceHealthEntry:
    service_id:           str
    composite_status:     str          # 'healthy' | 'degraded' | 'critical' | 'maintenance'
    composite_score:      float        # 0.0 (critical) → 1.0 (fully healthy)
    safe_to_act:          bool         # Derived: composite_score >= 0.7 AND no critical signals
    computed_at:          datetime
    ttl_seconds:          int          # After this, entry is stale and callers should not trust it
    signals:              list[Signal] # Contributing signals with individual scores

@dataclass
class Signal:
    name:         str
    value:        Any
    score:        float    # Signal's contribution: 0.0 → 1.0
    weight:       float    # Signal's weight in composite
    reason:       str      # Human-readable explanation
```

### Signal contributions

| Signal | Source | Score formula | Weight |
|---|---|---|---|
| `health_probe` | World state (ADR 0113) | 1.0=healthy, 0.5=degraded, 0.0=failing | 0.40 |
| `slo_budget` | ADR 0096 | budget_remaining_pct / 100 (capped at 0.0 for budget exhausted) | 0.20 |
| `drift_free` | Drift detector (ADR 0091) | 1.0=no drift, 0.5=drift detected, 0.0=critical drift | 0.15 |
| `open_incidents` | Closure loop (ADR 0126) | 1.0=none, 0.5=1 open, 0.0=≥2 open or critical severity | 0.15 |
| `pending_mutations` | Ledger (ADR 0115) | 1.0=none, 0.8=1 executing (non-conflicting), 0.3=conflict detected | 0.10 |

Composite score = weighted sum of signal scores.

Special cases that override the composite score to specific values regardless of signal weighting:

| Condition | Override value | Status |
|---|---|---|
| `maintenance_window_active` | 0.9 | `maintenance` |
| `health_probe = failing` AND `open_incidents ≥ 1` | 0.0 | `critical` |
| `slo_budget_remaining = 0` | 0.0 | `critical` |

### Schema

```sql
CREATE TABLE health.composite (
    service_id          TEXT PRIMARY KEY,
    composite_status    TEXT NOT NULL,
    composite_score     NUMERIC(4,3) NOT NULL,
    safe_to_act         BOOLEAN NOT NULL,
    signals             JSONB NOT NULL,
    computed_at         TIMESTAMPTZ NOT NULL,
    ttl_seconds         INTEGER NOT NULL DEFAULT 120
);

CREATE INDEX health_composite_status_idx ON health.composite (composite_status);
CREATE INDEX health_composite_safe_idx   ON health.composite (safe_to_act);
```

### Query API

```python
# platform/health/composite.py

health = HealthCompositeClient()

# Single service check — primary call for goal compiler and closure loop
entry = health.get("netbox")
if not entry.safe_to_act:
    print(f"Not safe to act on netbox: {entry.composite_status}")
    for sig in entry.signals:
        if sig.score < 0.5:
            print(f"  [{sig.name}] score={sig.score:.2f} — {sig.reason}")

# Platform-wide view — used by bootstrap (ADR 0123) and manifest (ADR 0132)
all_entries = health.get_all()
critical = [e for e in all_entries if e.composite_status == "critical"]
```

### Goal compiler integration

The goal compiler (ADR 0112) calls `health.get(service_id)` before compiling any mutation intent. If `safe_to_act` is False, the intent compilation fails immediately with `HEALTH_UNSAFE`:

```python
entry = health.get(intent.primary_service)
if not entry.safe_to_act:
    raise HealthUnsafe(
        service=intent.primary_service,
        status=entry.composite_status,
        score=entry.composite_score,
        reason=entry.signals[0].reason,
    )
```

This is a hard gate. An operator can bypass it by passing `--force-unsafe-health` to the CLI, which is recorded in the ledger and requires T4 trust (ADR 0125).

### Closure loop integration

The observation-to-action closure loop (ADR 0126) checks `safe_to_act` before transitioning from PROPOSING to EXECUTING. A run that would execute against a service in `critical` health is held in `PROPOSING` until either the health recovers or an operator approves the bypass.

### Platform CLI

```bash
$ lv3 health
SERVICE         STATUS       SCORE   SAFE   AGE
netbox          healthy      0.94    yes    18s
postgres        healthy      0.97    yes    22s
step-ca         degraded     0.61    no     31s   ← slo_budget: 38% remaining
windmill        healthy      0.89    yes    19s
keycloak        maintenance  0.90    yes    5s    ← maintenance window active

$ lv3 health netbox --verbose
composite_status: healthy
composite_score:  0.94

signals:
  health_probe      1.00  (weight 0.40)  HTTP 200 at 2026-03-24T14:31:02Z
  slo_budget        0.94  (weight 0.20)  94% error budget remaining
  drift_free        1.00  (weight 0.15)  No drift detected
  open_incidents    1.00  (weight 0.15)  No open incidents
  pending_mutations 0.80  (weight 0.10)  1 executing (converge-netbox, non-conflicting)
```

### NATS events

The composite index publisher emits `platform.health.degraded` and `platform.health.recovered` (ADR 0124) when a service's `composite_status` changes. These transitions are edge-triggered, not level-triggered: the event fires once on the transition, not on every 60-second refresh.

## Consequences

**Positive**

- Every component that needs a health check now calls a single, cheap local query rather than assembling health from 7 sources.
- The `safe_to_act` boolean is a forcing function: goal compiler, closure loop, and agents all use the same answer. There is no divergence between components that weight signals differently.
- The reason string in each signal gives agents a human-readable explanation of why a service is considered unsafe — something they can report to operators or include in triage context.
- Edge-triggered NATS events reduce alert noise compared to polling: `platform.health.degraded` fires once when health degrades, not repeatedly.

**Negative / Trade-offs**

- The fixed signal weights (health_probe: 0.40, slo_budget: 0.20, etc.) encode an opinion about what matters most. These weights are config-file values, but changing them requires a pull request. Operators who disagree with the weightings during an incident cannot adjust them at runtime.
- The 60-second refresh interval means the composite score may lag real health by up to a minute. For rapidly-flapping services, the composite score may not reflect the current state. The 120-second TTL is an additional safeguard, but callers should be aware that stale entries are possible.
- Adding a new health signal source requires both a schema change in the aggregator and a weight allocation that sums to 1.0 across all signals. This is a coordination cost.

## Boundaries

- The composite index is a read-only aggregation. It does not control or influence the underlying systems; it only reflects them.
- `safe_to_act: false` is advisory for diagnostic and read-only workflows. It is a hard gate only for mutation intents submitted through the goal compiler.
- Per-service overrides (e.g., declaring that a known-flaky health probe should be weighted lower for a specific service) are explicitly not supported. Overrides belong in the health probe contract (ADR 0064), not in the composite index.

## Related ADRs

- ADR 0064: Health probe contracts (health_probe signal source)
- ADR 0071: Agent observation loop (findings contribute to open_incidents signal)
- ADR 0080: Maintenance window protocol (maintenance_window_active override)
- ADR 0090: Platform CLI (`lv3 health` command)
- ADR 0091: Continuous drift detection (drift_free signal source)
- ADR 0092: Unified platform API gateway (`/v1/health` endpoint)
- ADR 0096: SLO error budget tracking (slo_budget signal source)
- ADR 0112: Deterministic goal compiler (checks safe_to_act before mutation intents)
- ADR 0113: World-state materializer (health_probe signal sourced from here)
- ADR 0115: Event-sourced mutation ledger (pending_mutations signal source)
- ADR 0123: Agent session bootstrap (platform_health surface now backed by composite index)
- ADR 0124: Platform event taxonomy (health.degraded / health.recovered events)
- ADR 0126: Observation-to-action closure loop (checks safe_to_act before EXECUTING)
- ADR 0132: Self-describing platform manifest (composite index is the health section)
