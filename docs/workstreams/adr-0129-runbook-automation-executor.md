# Workstream ADR 0129: Runbook Automation Executor

- ADR: [ADR 0129](../adr/0129-runbook-automation-executor.md)
- Title: Structured executor for multi-step runbooks with persisted run state, Windmill step dispatch, resumable escalations, and `lv3 runbook` operator entrypoints
- Status: merged
- Branch: `codex/adr-0129-runbook-automation-executor`
- Worktree: `.worktrees/adr-0129`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0066-mutation-audit-log`, `adr-0090-platform-cli`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: none
- Shared Surfaces: `scripts/runbook_executor.py`, `scripts/lv3_cli.py`, `config/windmill/scripts/`, `config/workflow-catalog.json`, `docs/runbooks/`

## Scope

- create `scripts/runbook_executor.py` with runbook discovery, templating, success-condition evaluation, sequential execution, retry and escalation handling, and persisted run records
- create `config/windmill/scripts/runbook-executor.py` as the worker wrapper
- update `scripts/lv3_cli.py` with `runbook execute`, `runbook status`, and `runbook approve`
- add `make runbook-executor` and register the workflow in `config/workflow-catalog.json`
- add operator documentation and ADR state for ADR 0129
- write focused tests for YAML and JSON runbooks plus the wrapper and CLI paths

## Non-Goals

- Parallel step execution
- Live application of the executor on the running platform
- Replacing the current repo-local run store with a shared service in this change

## Expected Repo Surfaces

- `scripts/runbook_executor.py`
- `config/windmill/scripts/runbook-executor.py`
- `scripts/lv3_cli.py`
- `config/workflow-catalog.json`
- `Makefile`
- `docs/adr/0129-runbook-automation-executor.md`
- `docs/runbooks/runbook-automation-executor.md`
- `docs/runbooks/renew-certificate.yaml`
- `docs/workstreams/adr-0129-runbook-automation-executor.md`
- `tests/test_runbook_executor.py`
- `tests/test_runbook_executor_windmill.py`
- `tests/test_lv3_cli.py`

## Expected Live Surfaces

- none yet; this workstream is repository automation only

## Verification

- run `python3 -m py_compile scripts/runbook_executor.py config/windmill/scripts/runbook-executor.py scripts/lv3_cli.py`
- run `uv run --with pytest --with pyyaml pytest tests/test_runbook_executor.py tests/test_runbook_executor_windmill.py tests/test_lv3_cli.py -q`
- run `uv run --with pyyaml python scripts/lv3_cli.py runbook execute docs/runbooks/renew-certificate.yaml --args service=grafana --dry-run`

## Merge Criteria

- focused executor, wrapper, and CLI tests pass
- ADR 0129 is marked implemented with the actual repo surfaces called out
- workflow catalog and runbook docs describe the new operator path

## Notes For The Next Assistant

- Run records persist under `.local/runbooks/runs/` and are not intended to be committed
- The current trace path uses mutation-audit events rather than a database-backed run store
- The operator-facing contract is intentionally small: load, execute, inspect, and resume
