# VM-Scoped Execution Lanes

## Purpose

This runbook covers the ADR 0154 execution-lane model that serialises or queues mutation work per VM instead of treating the whole platform as one implicit lane.

## Canonical Inputs

- lane catalog: [config/execution-lanes.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/execution-lanes.yaml)
- scheduler integration: [platform/scheduler/scheduler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py)
- lane registry: [platform/execution_lanes/registry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/execution_lanes/registry.py)
- Windmill dispatcher: [config/windmill/scripts/lane-scheduler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/lane-scheduler.py)

## Local Validation

1. `uvx --from pyyaml python scripts/execution_lanes.py --validate`
2. `make execution-lanes`
3. `make execution-lane-info LANE=lane:docker-runtime`
4. `uv run --with pytest --with pyyaml pytest -q tests/unit/test_execution_lanes.py tests/unit/test_scheduler_budgets.py tests/unit/test_intent_conflicts.py`

## Operational Checks

Use these local commands against the current checkout:

- `make lane-scheduler-loop`
- `make scheduler-watchdog-loop`

Expected results:

- the lane scheduler prints an `ok` status and reports the current queue snapshot
- the watchdog prints an `ok` status and cleans any finished active jobs

## Live Verification After `converge-windmill`

1. `curl -s -H "Authorization: Bearer $(cat .local/windmill/superadmin-secret.txt)" http://100.118.189.95:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Flane_scheduler`
2. `curl -s -H "Authorization: Bearer $(cat .local/windmill/superadmin-secret.txt)" http://100.118.189.95:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Fscheduler_watchdog`
3. `curl -s -H "Authorization: Bearer $(cat .local/windmill/superadmin-secret.txt)" http://100.118.189.95:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/lane_scheduler_every_2s" or .path=="f/lv3/scheduler_watchdog_every_30s") | {path, enabled, schedule}'`

Successful live apply means both scripts exist in the workspace and both schedules are enabled with the repo-managed cadence.

## Notes

- lane state is shared across worktrees by design because the registry writes under the git common-dir, not the individual worktree
- a queued intent is accepted work, not a failure; it should drain once the primary lane frees capacity
- service-level conflicts still apply on top of lane capacity, so two writes to the same service will continue to reject even if the lane itself has free slots
