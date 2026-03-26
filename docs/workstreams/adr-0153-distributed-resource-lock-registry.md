# Workstream ADR 0153: Distributed Resource Lock Registry

- ADR: [ADR 0153](../adr/0153-distributed-resource-lock-registry.md)
- Title: Worker-shared typed resource locks with TTL, hierarchy, deadlock-detector integration, and controller-local inspection tooling
- Status: merged
- Implemented In Repo Version: 0.150.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Branch: `codex/adr-0153-distributed-resource-lock-registry`
- Worktree: `.worktrees/adr-0153`
- Owner: codex
- Depends On: `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`, `adr-0127-intent-conflict-resolution`
- Conflicts With: `adr-0154-vm-scoped-execution-lanes`, `adr-0155-intent-queue-with-release-triggered-scheduling`
- Shared Surfaces: `platform/locking/`, `platform/scheduler/`, `platform/goal_compiler/`, `scripts/resource_lock_tool.py`, `Makefile`, `docs/runbooks/resource-lock-registry.md`

## Scope

- add the first repository implementation of ADR 0153 as a worker-shared lock registry with TTL pruning and hierarchy-aware conflict checks
- expose the registry through a controller-local inspection and mutation tool for operators and tests
- keep the lock contract stable for follow-on workstreams such as execution lanes, intent queue wake-ups, and deadlock detection
- restore the missing runbook and workstream metadata on later mainline revisions without regressing newer scheduler architecture

## Non-Goals

- claiming the JetStream KV backend is already the default runtime for the first repository implementation
- introducing lock-dashboard UI in this workstream
- marking the platform implementation as live-applied while host access remains unavailable

## Expected Repo Surfaces

- `platform/locking/`
- `scripts/resource_lock_tool.py`
- `Makefile`
- `docs/runbooks/resource-lock-registry.md`
- `docs/adr/0153-distributed-resource-lock-registry.md`
- `docs/workstreams/adr-0153-distributed-resource-lock-registry.md`
- `tests/test_resource_lock_registry.py`
- `tests/test_resource_lock_tool.py`

## Expected Live Surfaces

- the worker checkout creates `lv3-concurrency/lock-registry.json` under the git common dir on first lock activity
- the deadlock detector and any scheduler path using `platform.locking` read the same shared state file within that checkout
- a controller-local smoke test can inspect and mutate an explicitly selected registry state file through `scripts/resource_lock_tool.py`

## Verification

- `python3 -m py_compile platform/locking/*.py scripts/resource_lock_tool.py`
- `uv run --with pytest python -m pytest -q tests/test_deadlock_detector.py tests/test_resource_lock_registry.py tests/test_resource_lock_tool.py`
- `make ensure-resource-lock-registry`
- `make resource-locks`

## Merge Criteria

- the lock registry enforces TTL expiry and hierarchy-aware conflicts
- operators can ensure, list, acquire, release, and heartbeat locks through a documented repo-local tool
- README generated status output includes the ADR 0153 workstream again on current `main`

## Outcome

- repository implementation first merged in repo release `0.150.0`
- current `main` now carries the missing ADR 0153 runbook, workstream record, and current-main-compatible lock tool without reintroducing the earlier divergent scheduler branch
- focused lock-registry and lock-tool tests cover duplicate refresh, heartbeat, release-all, CLI round-trip, and conflict handling
- the first live apply remains blocked as of 2026-03-25 because SSH and API access to `proxmox_florin` were unavailable from the controller
