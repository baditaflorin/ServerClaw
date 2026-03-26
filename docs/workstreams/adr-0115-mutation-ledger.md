# Workstream ADR 0115: Event-Sourced Mutation Ledger

- ADR: [ADR 0115](../adr/0115-event-sourced-mutation-ledger.md)
- Title: Promote the mutation audit log into a fully typed, append-only event stream with before/after state and replay capability — the canonical operational memory for the whole platform
- Status: merged
- Branch: `codex/ws-0115-live-apply`
- Worktree: `.worktrees/ws-0115-live-apply`
- Owner: codex
- Depends On: `adr-0058-nats-event-bus`, `adr-0066-mutation-audit-log`, `adr-0098-postgres-ha`
- Conflicts With: `adr-0112-goal-compiler` (both add event types to ledger), `adr-0114-triage-engine` (writes triage reports to ledger)
- Shared Surfaces: `platform/ledger/`, `ledger.events` Postgres schema, `config/ledger-event-types.yaml`, NATS `ledger.*` topic namespace

## Scope

- create Postgres migration `migrations/0011_ledger_schema.sql` — `ledger.events` table with all columns from ADR 0115; append-only constraint via Postgres trigger that raises on UPDATE/DELETE
- create `config/ledger-event-types.yaml` — complete event type registry from ADR 0115
- create `platform/ledger/__init__.py`
- create `platform/ledger/writer.py` — `LedgerWriter.write()` method; NATS publish (fire-and-forget) after each insert
- create `platform/ledger/replay.py` — `LedgerReplayer.slice()` and `LedgerReplayer.project_state()` methods
- create `platform/ledger/reader.py` — helper queries: events by target, events by intent, events in time range
- create `windmill/ledger/migrate-audit-log.py` — one-time migration from `audit_log` (ADR 0066) to `ledger.events`; preserves original timestamps; sets `before_state` and `after_state` to NULL for legacy records
- add backward-compat view: `CREATE VIEW audit_log AS SELECT ... FROM ledger.events` for consumers that still use the old table name
- update existing mutation-writing workflows to use `LedgerWriter` instead of direct `audit_log` inserts (coordinate with owner of any workstreams that currently write to `audit_log`)
- write `tests/unit/test_ledger_writer.py` — test write path, NATS publish, append-only enforcement, duplicate event_id rejection

## Non-Goals

- Building the triage report reading path — that is ADR 0114's responsibility
- Building the search index over the ledger — that is ADR 0121's responsibility
- Defining retention archival beyond the schema design — ADR 0103 governs retention policy

## Expected Repo Surfaces

- `migrations/0011_ledger_schema.sql`
- `config/ledger-event-types.yaml`
- `platform/ledger/__init__.py`
- `platform/ledger/writer.py`
- `platform/ledger/replay.py`
- `platform/ledger/reader.py`
- `windmill/ledger/migrate-audit-log.py`
- `docs/adr/0115-event-sourced-mutation-ledger.md`
- `docs/workstreams/adr-0115-mutation-ledger.md`

## Expected Live Surfaces

- `ledger.events` table exists in Postgres and contains rows migrated from `audit_log`
- New platform mutations write to `ledger.events` via `LedgerWriter`
- `nats sub ledger.>` shows events being published after platform mutations
- `LedgerReplayer().slice(target_kind="service", target_id="netbox", from_ts=..., to_ts=...)` returns a non-empty list when netbox has been deployed recently

## Verification

- Run `pytest tests/unit/test_ledger_writer.py -v` → all tests pass
- Run the audit log migration workflow on the staging platform; confirm row counts match
- Attempt a direct `UPDATE ledger.events SET event_type = 'tampered'` → confirm the trigger raises and the update is rejected
- Trigger a `converge-netbox` deployment and confirm a `service.deployed` event with non-null `before_state` and `after_state` appears within 5 seconds

## Merge Criteria

- Unit tests pass
- Audit log migration completed successfully on at least one test environment
- Append-only constraint verified
- NATS publish verified
- `audit_log` backward-compat view in place and passing existing consumers

## Notes For The Next Assistant

- The `before_state` and `after_state` fields are JSONB and nullable. For the first wave of writers (Windmill workflows) that don't yet have state capture, set both to `null` and add `"state_capture": false` to `metadata`. This distinguishes "no state was captured" from "the state was empty".
- The NATS publish in `LedgerWriter.write()` must be fire-and-forget using `asyncio.create_task()` or a thread; never await the NATS publish inside the DB transaction.
- The append-only trigger should use `BEFORE UPDATE OR DELETE` → `RAISE EXCEPTION 'ledger.events is append-only'`. Do not use `RULE` syntax as it has surprising semantics with `RETURNING`.
- The `project_state` method in `LedgerReplayer` needs a well-defined state projection function per target_kind. Start with only `service` and `vm` kinds; return `NotImplementedError` for others until they are built out.

## Outcome

- merged in repo version `0.110.0`
- 2026-03-26 live apply verified the production Postgres ledger schema on platform version `0.130.20`, including the `audit_log` compatibility view, append-only trigger enforcement, and a live `execution.completed` row written from `docker-runtime-lv3`
- the live migration helper observed no SQL `audit_log` source table, so the first production rollout migrated `0` legacy rows and installed the compatibility view over an empty initial stream
- Windmill runtime automation was exercised repeatedly during the live apply, but concurrent `playbooks/windmill.yml` runs from other worktrees kept rewriting the same `docker-runtime-lv3` env surfaces; merge-to-main still needs one clean replay of `playbooks/windmill.yml` after shared-surface contention stops so `LV3_LEDGER_DSN` and `LV3_LEDGER_NATS_URL` stay durable in `/run/lv3-secrets/windmill/runtime.env`
