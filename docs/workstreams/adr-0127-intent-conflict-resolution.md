# Workstream ADR 0127: Intent Conflict Resolution

- ADR: [ADR 0127](../adr/0127-intent-deduplication-and-conflict-resolution.md)
- Title: Atomic intent claim registration, duplicate suppression, and conflict rejection for multi-agent workflow submissions
- Status: merged
- Branch: `codex/adr-0127-conflict-mgmt`
- Worktree: `../proxmox_florin_server-adr-0127`
- Owner: codex
- Depends On: `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: none
- Shared Surfaces: `platform/conflict/`, `platform/scheduler/`, `scripts/lv3_cli.py`, `config/workflow-catalog.json`, `config/ledger-event-types.yaml`

## Scope

- create `platform/conflict/__init__.py`, `platform/conflict/schema.py`, and `platform/conflict/engine.py`
- infer resource claims from workflow catalog metadata with conservative fallbacks for service, VM, and secret targets
- register claims atomically in a shared git-common-dir state file to handle separate worktrees and concurrent local agents
- integrate the conflict gate into `BudgetedWorkflowScheduler.submit()`
- reuse compiled intent IDs when present so scheduler and conflict events line up with the originating intent
- record `intent.claim_registered` and `intent.deduplicated` ledger events
- add `lv3 intent check` for operator-facing conflict preview
- extend workflow catalog validation for `resource_claims` and `dedup_window_seconds`
- add race-condition tests and overlapping-intent coverage
- document operations in `docs/runbooks/intent-conflict-resolution.md`

## Non-Goals

- distributed queueing or intent reordering
- transitive dependency locking beyond direct cascade warnings
- live platform application of the new gate from `main`

## Expected Repo Surfaces

- `platform/conflict/__init__.py`
- `platform/conflict/schema.py`
- `platform/conflict/engine.py`
- `platform/scheduler/scheduler.py`
- `scripts/lv3_cli.py`
- `scripts/workflow_catalog.py`
- `scripts/risk_scorer/context.py`
- `scripts/risk_scorer/models.py`
- `platform/goal_compiler/compiler.py`
- `platform/goal_compiler/schema.py`
- `config/workflow-catalog.json`
- `config/ledger-event-types.yaml`
- `docs/adr/0127-intent-deduplication-and-conflict-resolution.md`
- `docs/runbooks/intent-conflict-resolution.md`
- `docs/workstreams/adr-0127-intent-conflict-resolution.md`

## Expected Live Surfaces

- controller-side `lv3 intent check ...` reports resource claims and current conflict status
- overlapping submissions targeting the same service reject the later write before Windmill submission
- repeated identical mutation submissions within the dedup window return the recorded prior result

## Verification

- Run `uv run --with pytest python -m pytest tests/unit/test_goal_compiler.py tests/unit/test_scheduler_budgets.py tests/unit/test_intent_conflicts.py tests/test_lv3_cli.py -q`
- Run `uv run --with pytest python -m pytest tests/test_risk_scorer.py -q`
- Run `uv run --with pyyaml python scripts/workflow_catalog.py --validate`

## Merge Criteria

- overlapping scheduler submissions reject conflicting writes deterministically
- deduplication returns the prior result without a second Windmill submission
- the CLI preview shows inferred claims and gate status
- workflow catalog validation accepts the new metadata fields

## Outcome

- merged in repo version `0.122.0`
- live apply not yet performed from `main`
