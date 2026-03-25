# Release 0.153.0

- Date: 2026-03-25

## Summary
- Implemented ADR 0165 with deterministic workflow idempotency keys, shared idempotency-record storage, scheduler-side cached-result replay, and closure-loop trigger scoping to prevent duplicate workflow execution.
- Added `platform.idempotency`, the new `execution.idempotent_hit` ledger event type, and the operator-facing `lv3 intent status <intent_id>` status surface.
- Added the canonical Postgres schema migration at `migrations/0016_idempotency_store.sql`, a dedicated runbook, and focused regressions across the scheduler, CLI, conflict, and closure-loop paths.

## Platform Impact
- repository version advances to `0.153.0`; platform version remains `0.130.4` because the ADR 0165 live apply from `main` was blocked by an SSH timeout to the documented operator path during this turn

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
