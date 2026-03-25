# Workstream ADR 0165: Workflow Idempotency Keys and Double-Execution Prevention

- ADR: [ADR 0165](../adr/0165-workflow-idempotency-keys-and-double-execution-prevention.md)
- Title: Deterministic workflow idempotency keys, durable duplicate suppression, and operator-visible idempotent-hit status
- Status: merged
- Branch: `codex/live-apply-0165`
- Worktree: `.worktrees/live-apply-0165`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0058-nats-event-bus`, `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`, `adr-0126-observation-to-action-closure-loop`, `adr-0127-intent-conflict-resolution`
- Conflicts With: `adr-0119-budgeted-workflow-scheduler`, `adr-0126-observation-to-action-closure-loop`, `adr-0127-intent-conflict-resolution`
- Shared Surfaces: `platform/idempotency/`, `platform/scheduler/`, `platform/closure_loop/`, `scripts/lv3_cli.py`, `config/ledger-event-types.yaml`, `migrations/0016_idempotency_store.sql`

## Scope

- add `platform/idempotency/keys.py` for deterministic key construction
- add `platform/idempotency/store.py` with shared file-state fallback and Postgres support
- integrate scheduler submission/finalization with the idempotency store
- expose idempotent-hit status through `lv3 intent status`
- pass closure-loop trigger references as exact idempotency scopes
- add the Postgres schema migration and operator runbook

## Verification

- `uv run --with pytest pytest tests/unit/test_idempotency.py tests/unit/test_scheduler_budgets.py tests/unit/test_intent_conflicts.py tests/test_closure_loop_windmill.py tests/test_lv3_cli.py -q`
- `uv run python3 -m compileall platform/idempotency platform/scheduler scripts/lv3_cli.py platform/closure_loop/engine.py`

## Live Apply Status

- Repository implementation completed and merged for release `0.153.0`
- Live apply not completed in this turn
- Blocker observed on 2026-03-25: the documented operator SSH path to `ops@100.118.189.95` timed out from this execution environment, so the shared Postgres migration and any controller runtime rollout from `main` could not be verified live

## Notes For The Next Assistant

- the scheduler now prefers deterministic `idempotent_hit` over the older heuristic `duplicate` path when the same actor resubmits the same workflow inside the key window
- the live rollout still needs `migrations/0016_idempotency_store.sql` applied against the shared Postgres database before the Postgres-backed path can be claimed on the platform
- the git-common-dir file fallback already protects parallel local worktrees, so the repo behavior is still correct for controller-local development and tests
