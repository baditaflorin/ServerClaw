# ADR 0123: Agent Session Bootstrap and Context Hydration

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

When an agent (a Windmill workflow, a Claude Code session, or any other automation actor) begins a new session, it must understand the current state of the platform before it can take useful action. Today this context is assembled ad hoc:

- The goal compiler (ADR 0112) queries the world-state materializer (ADR 0113) immediately before compiling an intent.
- The triage engine (ADR 0114) fetches context at triage time, not at session start.
- The observation loop (ADR 0071) re-discovers drift state on every run without a shared starting snapshot.
- An agent responding to a Mattermost message (ADR 0057) has no structured mechanism to bootstrap its understanding of what is running, what is broken, or what is pending.

The consequence is repeated, overlapping reads from the same sources (Proxmox API, health probes, ledger, GlitchTip) by different components that start within seconds of each other. More importantly, there is no guarantee that two agents reasoning about the same platform instant are operating from the same snapshot. Race conditions in multi-agent scenarios are invisible because each agent silently re-reads state rather than agreeing on a shared context epoch.

A **context bootstrap call** — a single, cheap API call that returns a consistent, bounded snapshot of the platform at session start — eliminates redundant discovery, makes the shared epoch explicit, and gives agents a structured starting point that all downstream reasoning can reference.

## Decision

We will implement an **agent session bootstrap** service as a thin layer over the world-state materializer (ADR 0113), the mutation ledger (ADR 0115), the incident triage engine (ADR 0114), and the search fabric (ADR 0121). The bootstrap returns a typed `SessionContext` struct that any agent or workflow can call at startup.

### Bootstrap call

```python
# platform/bootstrap/client.py

from platform.bootstrap.client import BootstrapClient

ctx = BootstrapClient().hydrate(
    scope="full",           # 'full' | 'health_only' | 'mutations_only'
    actor_id="agent/triage-loop",
    max_age_seconds=120,    # Reject stale world-state snapshots older than this
)
```

The returned `SessionContext` is a frozen dataclass with a `context_id` (UUID) and a `captured_at` timestamp. All subsequent ledger events and intents written during this session should include the `context_id` so the post-session audit trail can reconstruct the information state the agent was operating from.

### SessionContext structure

```python
@dataclass(frozen=True)
class SessionContext:
    context_id:          str           # UUID, stable identifier for this bootstrap call
    captured_at:         datetime      # Wall-clock time of the snapshot
    actor_id:            str           # Identity that requested the bootstrap
    scope:               str           # 'full' | 'health_only' | 'mutations_only'

    # World state summary (from ADR 0113)
    platform_health:     dict          # Per-service health status: {'netbox': 'healthy', ...}
    vm_inventory:        list[dict]    # Running VMs: [{vmid, name, status, node}, ...]
    container_summary:   list[dict]    # Running containers: [{name, image, status, host}, ...]
    drift_surfaces:      dict          # Per-surface drift flags: {'opentofu': False, 'docker': True, ...}
    stale_surfaces:      list[str]     # Surfaces whose last refresh exceeds stale threshold

    # Recent mutations (from ADR 0115, last 2 hours by default)
    recent_mutations:    list[dict]    # [{intent_id, workflow_id, actor, target, event_type, ts}, ...]
    pending_intents:     list[dict]    # Intents compiled but not yet completed

    # Open incidents (from triage engine output, ADR 0114)
    open_incidents:      list[dict]    # [{incident_id, service, top_hypothesis, ts_fired}, ...]

    # Maintenance windows (from world state ADR 0113)
    active_maintenance:  list[dict]    # [{window_id, description, services, ends_at}, ...]

    # SLO status (from ADR 0096)
    slo_budget_status:   dict          # Per-service error budget: {'netbox': {'budget_remaining_pct': 94}, ...}
```

### Scope variants

| Scope | Included surfaces | Typical caller |
|---|---|---|
| `full` | All of the above | Triage engine, complex multi-step agents |
| `health_only` | platform_health, open_incidents, active_maintenance | Health-check workflows, alerting integrations |
| `mutations_only` | recent_mutations, pending_intents | Change-management workflows, approval reviewers |
| `minimal` | captured_at, actor_id, active_maintenance, stale_surfaces | Lightweight diagnostic tools |

### Staleness handling

If any requested surface has a last-refresh age exceeding `max_age_seconds`, the bootstrap client either:

1. Blocks and waits up to 10 seconds for the materializer (ADR 0113) to produce a fresh snapshot, then returns the refreshed context.
2. If the wait is exceeded, returns the stale snapshot with the surface name added to `stale_surfaces`. The caller decides whether stale data is acceptable for its purpose.

The bootstrap client never silently returns stale data as if it were fresh.

### Context propagation

Agents and workflows that receive a `SessionContext` should thread the `context_id` through all downstream calls:

```python
# All ledger writes during a session include the context_id
ledger.write(
    event_type="intent.compiled",
    target_id=intent.target,
    metadata={...},
    context_id=ctx.context_id,   # Links this event to the session snapshot
)

# The goal compiler accepts and forwards context_id
intent = compiler.compile(
    instruction="restart netbox",
    context=ctx,
)
```

This allows post-session analysis to ask: "What did this agent know when it made this decision?"

### Storage and TTL

Bootstrap snapshots are stored in Postgres `bootstrap.sessions`:

```sql
CREATE TABLE bootstrap.sessions (
    context_id      UUID PRIMARY KEY,
    actor_id        TEXT NOT NULL,
    scope           TEXT NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL,    -- Full SessionContext as JSON
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours'
);

CREATE INDEX bootstrap_sessions_actor_idx ON bootstrap.sessions (actor_id, captured_at DESC);
```

Snapshots expire after 24 hours. They exist solely for audit trail linkage; the world-state materializer (ADR 0113) remains the authoritative live source.

### Platform CLI integration

```bash
$ lv3 context show
context_id:    550e8400-e29b-41d4-a716-446655440000
captured_at:   2026-03-24T14:32:01Z
actor:         operator/live

platform_health:
  netbox        healthy
  postgres      healthy
  step-ca       healthy (cert expires 180d)
  windmill      healthy

open_incidents: none
active_maintenance: none
recent_mutations:
  [2026-03-24T12:01Z]  converge-netbox  completed  actor=codex/adr-0113-workstream
  [2026-03-24T13:45Z]  converge-step-ca completed  actor=operator/live

stale_surfaces: []
```

## Consequences

**Positive**

- Agents and operators begin every session from a shared, stamped snapshot rather than independent reads. Race conditions between agents reasoning about the same epoch are eliminated.
- The `context_id` threaded through ledger events makes it possible to reconstruct exactly what the platform looked like when any specific decision was made.
- Repeated discovery reads (world state, incidents, maintenance windows) from multiple concurrent components are collapsed into a single cached call per session.
- The `stale_surfaces` field makes staleness explicit and caller-visible rather than silently embedded in the data.

**Negative / Trade-offs**

- Agents that hold a `SessionContext` for a long time (e.g., a multi-hour workflow) will reason from an increasingly stale snapshot unless they periodically re-bootstrap. The bootstrap call is cheap but not free; callers must decide when to refresh.
- The 24-hour TTL on stored sessions means that very long-running workflows or forensic analysis beyond that window must reconstruct context from the ledger directly.
- Adding a new surface to the world-state materializer requires a corresponding field in `SessionContext`; this is a minor maintenance overhead.

## Boundaries

- The bootstrap client is a read-only service. It does not trigger refreshes of the world-state materializer; it reads whatever is available within the staleness threshold.
- The `SessionContext` is a snapshot, not a live subscription. Agents that need real-time updates should subscribe to the NATS event stream (ADR 0124) in addition to bootstrapping.
- This ADR does not define agent memory persistence across sessions; that is ADR 0130.

## Related ADRs

- ADR 0058: NATS event bus (real-time updates complement the static snapshot)
- ADR 0071: Agent observation loop (first major consumer of the bootstrap call)
- ADR 0090: Platform CLI (`lv3 context show`)
- ADR 0092: Unified platform API gateway (`/v1/bootstrap` endpoint)
- ADR 0096: SLO error budget tracking (slo_budget_status surface)
- ADR 0112: Deterministic goal compiler (accepts SessionContext to avoid redundant discovery)
- ADR 0113: World-state materializer (primary data source for all surfaces)
- ADR 0114: Rule-based incident triage engine (open_incidents surface)
- ADR 0115: Event-sourced mutation ledger (recent_mutations surface; context_id propagation)
- ADR 0124: Platform event taxonomy (real-time complement to the static SessionContext)
- ADR 0130: Agent state persistence (persists findings derived from a SessionContext)
- ADR 0132: Self-describing platform manifest (machine-readable summary built from SessionContext)
