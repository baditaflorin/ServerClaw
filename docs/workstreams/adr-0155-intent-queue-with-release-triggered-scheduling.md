# Workstream ADR 0155: Intent Queue with Release-Triggered Scheduling

- ADR: [ADR 0155](../adr/0155-intent-queue-with-release-triggered-scheduling.md)
- Title: Queue workflow-busy and conflict-blocked intents behind a durable scheduler queue with dispatcher replay and Windmill safety scheduling
- Status: merged
- Implemented In Repo Version: 0.158.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Branch: `codex/adr-0155-main-live`
- Worktree: `/private/tmp/proxmox_florin_server-main-0155-v2`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0119-budgeted-workflow-scheduler`, `adr-0127-intent-conflict-resolution`, `adr-0154-vm-scoped-execution-lanes`, `adr-0162-deadlock-detector`
- Conflicts With: none
- Shared Surfaces: `platform/intent_queue/`, `platform/scheduler/`, `scripts/lv3_cli.py`, `scripts/intent_queue_dispatcher.py`, `config/windmill/scripts/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `config/ledger-event-types.yaml`, `docs/runbooks/intent-queue.md`

## Scope

- add the missing ADR 0155 scheduler-owned queue on top of the current ADR 0154 lane scheduler and ADR 0162 deadlock queue surfaces
- queue workflow-concurrency and intent-conflict rejections when callers opt into `queue_if_conflicted`
- replay queued intents through a repo-managed dispatcher script and Windmill wrapper
- expose ADR 0155 queue flags through `lv3 run`
- document queue state, manual dispatch, and live verification

## Non-Goals

- replacing the ADR 0154 lane queue or its two-second lane scheduler
- replacing the ADR 0162 deadlock queue store
- adding a JetStream or Postgres-backed runtime queue on this branch

## Expected Repo Surfaces

- `platform/intent_queue/scheduler_store.py`
- `platform/scheduler/scheduler.py`
- `scripts/lv3_cli.py`
- `scripts/intent_queue_dispatcher.py`
- `config/windmill/scripts/intent-queue-dispatcher.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `config/ledger-event-types.yaml`
- `docs/adr/0155-intent-queue-with-release-triggered-scheduling.md`
- `docs/workstreams/adr-0155-intent-queue-with-release-triggered-scheduling.md`
- `docs/runbooks/intent-queue.md`

## Expected Live Surfaces

- Windmill workspace `lv3` contains the script `f/lv3/intent_queue_dispatcher`
- Windmill schedule `f/lv3/intent_queue_dispatcher_every_minute` is present and enabled
- the Windmill worker checkout contains `scripts/intent_queue_dispatcher.py`
- queued conflict-blocked intents can be drained with queue position and dispatch ledger events recorded

## Verification

- `python3 -m py_compile platform/intent_queue/__init__.py platform/intent_queue/store.py platform/intent_queue/scheduler_store.py platform/scheduler/scheduler.py scripts/lv3_cli.py scripts/intent_queue_dispatcher.py config/windmill/scripts/intent-queue-dispatcher.py`
- `uv run --with pytest python -m pytest tests/unit/test_scheduler_budgets.py tests/unit/test_intent_conflicts.py tests/unit/test_execution_lanes.py tests/unit/test_scheduler_intent_queue.py tests/test_lv3_cli.py -q`
- `make syntax-check-windmill`
- `make live-apply-service service=windmill env=production`

## Merge Criteria

- `queue_if_conflicted` returns `queued` for workflow-busy and conflict-rejected submissions
- the dispatcher requeues blocked items and dispatches them once the blocking claim clears
- Windmill seeds the dispatcher script and enabled minute safety schedule
- the runbook explains queue state paths and the manual dispatcher entrypoint

## Notes For The Next Assistant

- the current `main` branch already has ADR 0154 lane queueing; keep that queue distinct from the ADR 0155 scheduler intent queue
- the current `platform/intent_queue/store.py` is still used by ADR 0162 deadlock detection and should not be repurposed
- do not mark this workstream `live_applied` or bump `platform_version` until the merged Windmill runtime converge and script/schedule verification are complete
