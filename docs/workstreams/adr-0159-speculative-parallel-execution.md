# Workstream ADR 0159: Speculative Parallel Execution with Compensating Transactions

- ADR: [ADR 0159](../adr/0159-speculative-parallel-execution-with-compensating-transactions.md)
- Title: Opt-in speculative execution for reversible workflows on top of the current scheduler and conflict registry
- Status: merged
- Branch: `codex/live-apply-0159`
- Worktree: `../proxmox-host_server-live-apply-0159`
- Owner: codex
- Depends On: `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`, `adr-0124-platform-event-taxonomy`, `adr-0127-intent-conflict-resolution`
- Conflicts With: none
- Shared Surfaces: `platform/scheduler/`, `platform/conflict/`, `platform/goal_compiler/`, `scripts/lv3_cli.py`, `scripts/workflow_catalog.py`, `config/ledger-event-types.yaml`

## Scope

- add speculative workflow policy support to the scheduler budget loader and workflow catalog validator
- add a speculative execution helper module for probe loading, rollback argument shaping, and persisted speculative state
- teach the conflict registry to register a speculative writer even when it collides with an existing write claim
- teach the scheduler to skip the pessimistic lock for speculative workflows, run the conflict probe, and launch the compensating workflow on loss
- add goal-compiler and CLI support for explicit speculative opt-in
- record speculative execution lifecycle events in the ledger
- cover the commit and rollback paths with regression tests
- document authoring and operator usage in a dedicated runbook

## Non-Goals

- marking existing production workflows speculative-eligible by default
- replacing the current pessimistic scheduler path for ordinary workflows
- claiming a live platform version bump without a speculative-enabled workflow applied from `main`

## Expected Repo Surfaces

- `platform/scheduler/budgets.py`
- `platform/scheduler/scheduler.py`
- `platform/scheduler/speculative.py`
- `platform/conflict/engine.py`
- `platform/goal_compiler/compiler.py`
- `platform/goal_compiler/schema.py`
- `scripts/lv3_cli.py`
- `scripts/workflow_catalog.py`
- `config/ledger-event-types.yaml`
- `docs/adr/0159-speculative-parallel-execution-with-compensating-transactions.md`
- `docs/runbooks/speculative-workflow-execution.md`
- `docs/workstreams/adr-0159-speculative-parallel-execution.md`

## Expected Live Surfaces

- `lv3 run --allow-speculative ...` compiles an intent with `execution_mode: speculative` when the workflow is eligible
- speculative conflicts are registered instead of being rejected immediately
- successful speculative runs emit `execution.speculative_committed`
- losing speculative runs emit `execution.speculative_rolled_back` after the compensating workflow completes

## Verification

- run `uv run --with pytest --with pyyaml python -m pytest tests/unit/test_goal_compiler.py tests/unit/test_intent_conflicts.py tests/unit/test_scheduler_budgets.py tests/unit/test_ledger_writer.py tests/test_lv3_cli.py -q`
- run `uv run --with pyyaml python scripts/workflow_catalog.py --validate`
- run `python3 -m py_compile platform/goal_compiler/compiler.py platform/goal_compiler/schema.py platform/conflict/engine.py platform/scheduler/budgets.py platform/scheduler/scheduler.py platform/scheduler/speculative.py scripts/workflow_catalog.py scripts/lv3_cli.py`

## Merge Criteria

- speculative workflows remain opt-in
- the scheduler commit path and rollback path are both covered by tests
- the workflow catalog rejects incomplete speculative metadata
- the CLI exposes speculative opt-in without changing default behaviour

## Outcome

- merged in repo version `0.144.0`
- no live platform version change is claimed; the framework is repository-side until a production workflow is explicitly opted in and applied from `main`
