# ADR 0115: Event-Sourced Mutation Ledger

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.110.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

ADR 0066 established a mutation audit log: every platform mutation is recorded with actor, target, action, and outcome. This log is useful for post-incident review but it is narrow in scope and flat in structure. It records that something happened but not what the world looked like before, what it looked like after, or what the operator intended when they triggered the action.

The platform now has enough moving parts that operational memory is becoming a liability:

- An agent workflow that ran yesterday has no durable record of what state it saw when it made decisions.
- Rollback analysis requires manually correlating the audit log entry with an external diff; there is no before/after state embedded in the record.
- Incident replay (needed for the triage engine, ADR 0114) requires reconstructing state from multiple sources rather than reading a single ordered stream.
- The goal compiler (ADR 0112) compiles intents and the workflow scheduler (ADR 0119) executes them, but neither has a canonical store to write their lifecycle events to.

Event sourcing addresses this by treating every platform mutation as an immutable, typed, ordered event with full before/after context. Operational state becomes derivable from the event stream.

## Decision

We will promote the mutation audit log into a full **event-sourced mutation ledger** by replacing the flat audit log table with a structured event stream schema in Postgres.

### Event schema

```sql
CREATE TABLE ledger.events (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL DEFAULT gen_random_uuid(),
    event_type      TEXT NOT NULL,          -- see event type registry below
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor           TEXT NOT NULL,          -- 'operator:alice', 'agent:codex', 'scheduler:windmill'
    actor_intent_id UUID,                   -- links to ExecutionIntent if compiled (ADR 0112)
    tool_id         TEXT,                   -- tool from tool registry (ADR 0069)
    target_kind     TEXT NOT NULL,          -- 'service', 'host', 'secret', 'cert', 'workflow', ...
    target_id       TEXT NOT NULL,          -- e.g. 'netbox', 'proxmox-host-lv3', 'platform/netbox/db'
    before_state    JSONB,                  -- snapshot of relevant state before mutation (nullable)
    after_state     JSONB,                  -- snapshot of state after mutation (nullable)
    receipt         JSONB,                  -- tool execution receipt (stdout, exit code, duration)
    metadata        JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT ledger_events_event_id_unique UNIQUE (event_id)
);

CREATE INDEX ledger_events_occurred_at_idx ON ledger.events (occurred_at DESC);
CREATE INDEX ledger_events_target_idx ON ledger.events (target_kind, target_id);
CREATE INDEX ledger_events_actor_intent_idx ON ledger.events (actor_intent_id) WHERE actor_intent_id IS NOT NULL;
```

The table is append-only. No UPDATE or DELETE operations are permitted. Corrections are new events with `event_type: correction` pointing to the original `event_id` via `metadata.corrects`.

### Event type registry

```yaml
# config/ledger-event-types.yaml

# Intent lifecycle
- intent.compiled
- intent.approved
- intent.rejected
- intent.expired

# Execution lifecycle
- execution.started
- execution.completed
- execution.failed
- execution.aborted
- execution.budget_exceeded       # see ADR 0119

# Service mutations
- service.deployed
- service.rolled_back
- service.restarted
- service.config_changed

# Secret management
- secret.rotated
- secret.accessed
- secret.expiry_extended

# Infrastructure
- host.provisioned
- host.decommissioned
- vm.created
- vm.destroyed
- vm.snapshot_taken

# Certificate management
- cert.issued
- cert.renewed
- cert.revoked

# Observability
- alert.fired
- triage.report_created           # see ADR 0114
- incident.opened
- incident.resolved

# Corrections and annotations
- correction
- operator.annotation
```

### Writer API

All platform components write to the ledger through a single module:

```python
# platform/ledger/writer.py

from platform.ledger.writer import LedgerWriter

ledger = LedgerWriter()

ledger.write(
    event_type="service.deployed",
    actor="operator:florin",
    actor_intent_id="550e8400-e29b-41d4-a716-446655440000",
    tool_id="ansible-playbook",
    target_kind="service",
    target_id="netbox",
    before_state=ws.get_at("service_health", at=start_time),
    after_state=ws.get("service_health"),
    receipt={"exit_code": 0, "changed": 3, "duration_s": 42},
)
```

The writer publishes a `platform.mutation.recorded` message to NATS (ADR 0058) after each successful insert. Downstream consumers (the triage engine, the dashboard, the search fabric) react to these events in real time.

### Replay API

The ledger supports reconstruction of platform state at any point in time:

```python
# platform/ledger/replay.py

from platform.ledger.replay import LedgerReplayer

replayer = LedgerReplayer()

# All events touching netbox between two timestamps
events = replayer.slice(
    target_kind="service",
    target_id="netbox",
    from_ts="2026-03-24T00:00:00Z",
    to_ts="2026-03-24T12:00:00Z",
)

# Reconstruct the state of netbox at a specific moment
state_at = replayer.project_state("service:netbox", at="2026-03-24T06:00:00Z")
```

### Migration from ADR 0066

The existing `audit_log` table from ADR 0066 is migrated to `ledger.events` via a one-time Windmill workflow. Historical audit records that lack `before_state` and `after_state` are inserted with those fields as NULL. The ADR 0066 schema is deprecated and the `audit_log` table aliased to a view over `ledger.events` for backward compatibility until all consumers are updated.

## Consequences

**Positive**

- Every action on the platform has a durable, ordered, typed record with before/after state. Post-incident review is a ledger query, not a manual correlation exercise.
- The goal compiler, workflow scheduler, and triage engine all write to the same stream; the ledger becomes the single coherent operational memory for the platform.
- Rollback analysis is deterministic: given a `before_state` snapshot, the rollback path has a concrete target state.
- The replay API makes incident timeline reconstruction a first-class operation rather than an archaeological exercise.

**Negative / Trade-offs**

- The schema requires `before_state` and `after_state` discipline from every writer. Lazy writers that omit these fields degrade the ledger's usefulness for replay.
- Append-only tables grow without bound. A retention policy (ADR 0103) must define how long events are kept and how they are archived.
- The NATS publish on every write adds a small latency cost. Writers must not block on NATS delivery; publish must be fire-and-forget.

## Implementation Notes

- The repository now ships the Postgres schema migration at [migrations/0011_ledger_schema.sql](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0011_ledger_schema.sql), the canonical registry at [config/ledger-event-types.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/ledger-event-types.yaml), and the runtime modules at [platform/ledger/writer.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/ledger/writer.py), [platform/ledger/reader.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/ledger/reader.py), and [platform/ledger/replay.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/ledger/replay.py).
- A one-time migration helper now lives at [windmill/ledger/migrate-audit-log.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/windmill/ledger/migrate-audit-log.py) and installs the backward-compatible `audit_log` view after moving legacy rows into `ledger.events`.
- The existing controller-side emitter at [scripts/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/mutation_audit.py) now dual-writes legacy mutation events into the ledger when `LV3_LEDGER_DSN` is configured, preserving the JSONL/Loki sinks while the platform is migrated.
- The 2026-03-26 production live apply ran the schema against the shared `postgres` database on `postgres-lv3`, found no legacy SQL `audit_log` table to migrate, and installed the compatibility `audit_log` view with zero migrated rows because the live ADR 0066 sink was still JSONL/Loki-only.
- The same live apply verified a guest-side dual-write from `docker-runtime-lv3` into `ledger.events`, confirmed the `audit_log` compatibility view exposed that row, and confirmed the append-only trigger rejected an `UPDATE`.
- The live NATS broker on `docker-runtime-lv3` now carries mutation fan-out on `platform.mutation.recorded` inside the existing `PLATFORM_EVENTS` stream, so downstream subscribers keep the `platform.>` retention contract while ADR 0276 adds dedicated non-platform domain streams for `secret.rotation.*` and `rag.document.*`.
- A 2026-03-27 replay from the latest `origin/main` re-projected `LV3_LEDGER_DSN` and `LV3_LEDGER_NATS_URL` into the Windmill runtime, recovered the worker containers after a startup race, and verified a new guest-side ledger row with correlation id `ws0115-main-ledger-emit-20260327T044831Z`.
- The 2026-03-27 replay from the latest `origin/main` confirmed the Windmill runtime ledger projection on both `/run/lv3-secrets/windmill/runtime.env` and the live worker container environment after targeted service recovery; the remaining follow-up is the broader post-restart `sync_windmill_seed_scripts.py` connection loss, not the ADR 0115 ledger wiring itself.

## Boundaries

- The ledger stores operational events. It does not store secrets, credentials, or PII.
- The ledger is append-only. No mutation-of-mutations is permitted; corrections are new events.
- The ledger is the authority for what happened; the world-state materializer (ADR 0113) is the authority for what the platform looks like right now.

## Related ADRs

- ADR 0058: NATS event bus (ledger event fan-out)
- ADR 0066: Mutation audit log (superseded by this ADR)
- ADR 0098: Postgres HA (underlying storage)
- ADR 0103: Data classification and retention policy (event retention rules)
- ADR 0112: Deterministic goal compiler (writes intent lifecycle events)
- ADR 0113: World-state materializer (provides before/after state snapshots)
- ADR 0114: Rule-based incident triage (reads recent mutations, writes triage reports)
- ADR 0116: Change risk scoring (reads historical failure rates from the ledger)
- ADR 0119: Budgeted workflow scheduler (writes execution lifecycle events)
- ADR 0121: Local search and indexing fabric (indexes ledger events for operator search)
