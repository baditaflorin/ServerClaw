# ADR 0157 Workstream

- ADR: 0157
- Title: Per-VM concurrency budget and resource reservation
- Status: in_progress
- Branch: codex/live-apply-0157
- Worktree: .worktrees/live-apply-0157
- Owner: codex
- Depends On:
  - adr-0119-budgeted-workflow-scheduler
- Conflicts With:
  - adr-0153-distributed-resource-lock-registry
  - adr-0154-vm-scoped-execution-lanes
- Shared Surfaces:
  - config/execution-lanes.yaml
  - config/workflow-catalog.json
  - config/workflow-defaults.yaml
  - platform/scheduler
  - docs/runbooks/budgeted-workflow-scheduler.md
  - docs/runbooks/per-vm-concurrency-budgets.md
  - playbooks/windmill.yml
  - roles/windmill_runtime

## Scope

- implement lane-level resource reservations in the scheduler
- make the reservation and lane catalogs repo-validated
- apply the updated worker checkout live through the Windmill service path
- update the ADR and release metadata after the mainline live apply is complete

## Non-Goals

- full ADR 0153 distributed resource locks
- queue-driven lane scheduling from ADR 0155
- dynamic live budget tuning from Proxmox telemetry beyond the static lane catalog

## Expected Repo Surfaces

- `config/execution-lanes.yaml`
- `config/workflow-defaults.yaml`
- `config/workflow-catalog.json`
- `platform/scheduler/`
- `scripts/execution_lanes.py`
- `tests/unit/test_scheduler_budgets.py`
- `docs/adr/0157-per-vm-concurrency-budget-and-resource-reservation.md`

## Expected Live Surfaces

- `/srv/proxmox_florin_server/config/execution-lanes.yaml` on `docker-runtime-lv3`
- `/srv/proxmox_florin_server/platform/scheduler/` on `docker-runtime-lv3`
- `/srv/proxmox_florin_server/scripts/execution_lanes.py` on `docker-runtime-lv3`

## Verification

- `uv run --with pytest python -m pytest tests/unit/test_scheduler_budgets.py -q`
- `uv run --with pytest python -m pytest tests/unit/test_intent_conflicts.py -q`
- `python3 scripts/workflow_catalog.py --validate`
- `python3 scripts/execution_lanes.py --validate`
- `make validate`
- `make live-apply-service service=windmill env=production`

## Merge Criteria

- scheduler rejects hard over-budget mutations before Windmill submission
- soft-policy lanes allow execution and return an explicit finding payload
- reservations are released when runs finish
- the lane catalog is validated in the repo gate
- mainline live apply and receipt are recorded

## Notes For The Next Assistant

- if live apply is blocked, leave the receipt uncommitted and keep the ADR implementation status honest
