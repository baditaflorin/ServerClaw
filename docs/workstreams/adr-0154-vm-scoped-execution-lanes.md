# Workstream ADR 0154: VM-Scoped Parallel Execution Lanes

- ADR: [ADR 0154](../adr/0154-vm-scoped-parallel-execution-lanes.md)
- Title: per-VM execution lane catalog, queueing scheduler path, and Windmill lane dispatcher
- Status: live_applied
- Branch: `codex/adr-0154-vm-scoped-execution-lanes`
- Worktree: `.worktrees/adr-0154`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0075-service-capability-catalog`, `adr-0112-goal-compiler`, `adr-0119-budgeted-workflow-scheduler`, `adr-0127-intent-conflict-resolution`
- Conflicts With: none
- Shared Surfaces: `config/execution-lanes.yaml`, `platform/execution_lanes/`, `platform/scheduler/`, `platform/goal_compiler/`, `scripts/risk_scorer/`, `scripts/lv3_cli.py`, `config/windmill/scripts/`, `roles/windmill_runtime`, `docs/runbooks/`

## Scope

- add the canonical execution-lane catalog in `config/execution-lanes.yaml`
- add resolver and shared state primitives under `platform/execution_lanes/`
- extend the scheduler so lane saturation queues work instead of rejecting it
- extend the watchdog so queued asynchronous jobs release lane leases and conflict claims
- surface `required_lanes` through the goal compiler, direct workflow intents, and the CLI handoff path
- seed the lane scheduler and scheduler watchdog into Windmill and enable their repo-managed schedules
- document the operating model in a dedicated runbook and this ADR

## Non-Goals

- replacing the existing conflict registry with the later distributed lock backend
- implementing every future cross-VM coordination ADR in this change
- adding a full lane dashboard to every UI surface in the first release

## Expected Repo Surfaces

- `config/execution-lanes.yaml`
- `platform/execution_lanes/catalog.py`
- `platform/execution_lanes/registry.py`
- `platform/scheduler/scheduler.py`
- `platform/scheduler/watchdog.py`
- `platform/goal_compiler/compiler.py`
- `platform/goal_compiler/schema.py`
- `scripts/risk_scorer/context.py`
- `scripts/risk_scorer/models.py`
- `scripts/lv3_cli.py`
- `scripts/execution_lanes.py`
- `config/windmill/scripts/lane-scheduler.py`
- `windmill/scheduler/watchdog-loop.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `docs/runbooks/vm-scoped-execution-lanes.md`

## Expected Live Surfaces

- Windmill now seeds `f/lv3/lane_scheduler` and `f/lv3/scheduler_watchdog`
- the live Windmill workspace keeps a two-second lane-dispatch schedule enabled
- queued scheduler intents on a saturated lane are eventually dispatched once the lane frees up
- completed queued jobs release both their conflict claim and their lane lease without manual cleanup

## Verification

- `uvx --from pyyaml python scripts/execution_lanes.py --validate`
- `uv run --with pytest --with pyyaml pytest -q tests/unit/test_execution_lanes.py tests/unit/test_scheduler_budgets.py tests/unit/test_intent_conflicts.py`
- `python3 -m py_compile platform/execution_lanes/*.py platform/scheduler/*.py platform/goal_compiler/*.py scripts/execution_lanes.py scripts/lv3_cli.py scripts/risk_scorer/*.py config/windmill/scripts/lane-scheduler.py windmill/scheduler/watchdog-loop.py`
- `uv run --with jsonschema --with pyyaml python scripts/validate_repository_data_models.py --validate`
- `make live-apply-service service=windmill env=production`

## Merge Criteria

- execution-lane catalog validates
- queue saturation returns `queued` instead of a hard scheduler rejection
- dispatch loop reseeds successfully into Windmill
- live converge proves the new script and schedule are present on the worker checkout

## Outcome

- repository implementation completed in `0.149.0`
- platform version `0.131.0` is the first live claim of ADR 0154 from `main`
- the live Windmill runtime now owns both the lane dispatcher and the scheduler watchdog schedules
