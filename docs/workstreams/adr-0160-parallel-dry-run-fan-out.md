# Workstream ADR 0160: Parallel Dry-Run Fan-Out

- ADR: [ADR 0160](../adr/0160-parallel-dry-run-fan-out-for-intent-batch-validation.md)
- Title: Controller-local batch validation that compiles multiple intents, fans out semantic dry-runs in parallel, detects cross-intent conflicts from the combined result set, and emits a staged execution plan
- Status: merged
- Branch: `codex/adr-0160-live-apply`
- Worktree: `.worktrees/adr-0160-live-apply`
- Owner: codex
- Depends On: `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`, `adr-0120-dry-run-diff-engine`, `adr-0127-intent-conflict-resolution`
- Conflicts With: none
- Shared Surfaces: `platform/goal_compiler/`, `scripts/lv3_cli.py`, `config/ledger-event-types.yaml`, `docs/runbooks/parallel-intent-batch-validation.md`

## Scope

- extend `GoalCompiler` with `compile_batch()` and `validate_batch()`
- add `platform/goal_compiler/batch.py` with:
  - parallel semantic dry-run fan-out
  - combined resource-touch aggregation from semantic diffs and resource claims
  - cross-intent conflict classification
  - staged execution-plan generation
  - optional `intent.batch_plan` ledger emission
- add `lv3 intent batch` for operator-facing batch-plan preview
- register `intent.batch_plan` in `config/ledger-event-types.yaml`
- add focused unit and CLI regression coverage
- document the workflow in `docs/runbooks/parallel-intent-batch-validation.md`

## Non-Goals

- stage-aware scheduler submission through ADR 0155
- Windmill-native batch orchestration
- ops-portal rendering of batch plans
- any live platform version bump from this repo-only implementation

## Expected Repo Surfaces

- `platform/goal_compiler/compiler.py`
- `platform/goal_compiler/batch.py`
- `platform/goal_compiler/__init__.py`
- `scripts/lv3_cli.py`
- `config/ledger-event-types.yaml`
- `tests/unit/test_goal_compiler.py`
- `tests/unit/test_intent_batch_planner.py`
- `tests/test_lv3_cli.py`
- `docs/adr/0160-parallel-dry-run-fan-out-for-intent-batch-validation.md`
- `docs/runbooks/parallel-intent-batch-validation.md`
- `docs/workstreams/adr-0160-parallel-dry-run-fan-out.md`

## Expected Live Surfaces

- controller-side `lv3 intent batch --instruction ... --instruction ...` renders a staged execution plan
- independent intents share the same parallel stage
- conflicting writes are rejected before any scheduler submission
- restart-vs-config pairs are ordered into successive stages

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/unit/test_goal_compiler.py tests/unit/test_intent_batch_planner.py tests/test_lv3_cli.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- batch compilation preserves instruction order and actor policy checks
- dry-run fan-out executes concurrently instead of serially
- combined-diff conflict analysis produces both rejection and ordering cases
- the CLI emits a durable `intent.batch_plan` event when previewing a batch

## Outcome

- merged in repo version `0.144.0`
- live apply not yet performed from `main`
