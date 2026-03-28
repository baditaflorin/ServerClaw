# Workstream WS-0204: Self-Correcting Automation Loops Live Apply

- ADR: [ADR 0204](../adr/0204-self-correcting-automation-loops.md)
- Title: Governed correction-loop contracts plus live observation-loop replay
- Status: live_applied
- Branch: `codex/ws-0204-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0204-live-apply`
- Owner: codex
- Depends On: `adr-0204-architecture-governance`, `adr-0126-observation-to-action-closure-loop`, `adr-0172-watchdog-escalation-and-stale-job-self-healing`
- Conflicts With: none
- Shared Surfaces: `config/correction-loops.json`, `scripts/correction_loops.py`, `platform/closure_loop/`, `config/windmill/scripts/platform-observation-loop.py`, `scripts/live_apply_receipts.py`, `scripts/workflow_catalog.py`, `scripts/command_catalog.py`, `scripts/validate_repository_data_models.py`, `docs/runbooks/`, `workstreams.yaml`

## Scope

- add a governed ADR 0204 correction-loop catalog that explicitly covers every mutating workflow plus the live observation and watchdog runtimes
- enforce the catalog in repository validation and merge-safe config handling
- expose the resolved correction-loop contract through existing workflow and command inspection surfaces
- wire the live observation-loop runtime to persist and report its governed correction-loop contract
- replay the live Windmill observation surface, capture a production receipt, and verify the correction-loop metadata end to end

## Non-Goals

- redesigning every mutable workflow implementation around a brand-new execution engine
- enabling autonomous destructive recovery outside the already documented approval boundaries
- updating protected main-integration files on this branch before the final merged-main step

## Expected Repo Surfaces

- `docs/adr/0204-self-correcting-automation-loops.md`
- `docs/workstreams/ws-0204-live-apply.md`
- `docs/runbooks/observation-to-action-closure-loop.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/validate-repository-automation.md`
- `config/correction-loops.json`
- `config/ansible-role-idempotency.yml`
- `docs/schema/correction-loop-catalog.schema.json`
- `config/merge-eligible-files.yaml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `scripts/correction_loops.py`
- `scripts/incident_triage.py`
- `scripts/live_apply_receipts.py`
- `scripts/sync_windmill_seed_schedules.py`
- `scripts/workflow_catalog.py`
- `scripts/command_catalog.py`
- `scripts/validate_repository_data_models.py`
- `platform/closure_loop/engine.py`
- `config/windmill/scripts/platform-observation-loop.py`
- `tests/test_correction_loops.py`
- `tests/unit/test_closure_loop.py`
- `tests/test_closure_loop_windmill.py`
- `tests/test_incident_triage.py`
- `tests/test_live_apply_receipts.py`
- `tests/test_config_merge_repo_surfaces.py`
- `tests/test_windmill_operator_admin_app.py`
- `workstreams.yaml`

## Expected Live Surfaces

- the seeded Windmill script `f/lv3/platform_observation_loop` returns the governed correction-loop id in its live output
- durable closure-loop run records on the worker checkout now carry the ADR 0204 correction-loop snapshot
- the live observation runtime uses the catalog retry budget instead of an ad hoc hard-coded self-correction ceiling

## Verification

- `python3 scripts/correction_loops.py --validate`
- `uv run --with pytest python -m pytest -q tests/test_correction_loops.py tests/unit/test_closure_loop.py tests/test_closure_loop_windmill.py tests/test_live_apply_receipts.py tests/test_config_merge_repo_surfaces.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- `make validate`
- `make converge-windmill`
- authenticated `jobs/run_wait_result` invocation of `f/lv3/platform_observation_loop`

## Merge Criteria

- every mutating workflow is covered by exactly one governed correction-loop contract
- workflow and command inspection surfaces show the applicable correction-loop metadata
- the live observation loop persists and reports its correction-loop id on production
- the live-apply receipt records the correction-loop evidence clearly and calls out any remaining main-integration work

## Outcome

- branch-local live apply succeeded on 2026-03-28 and the authenticated Windmill observation replay now returns `status: ok` with `correction_loop_id: runtime_self_correction_watchers`
- the durable worker closure-loop state persisted the governed correction-loop snapshot for run `71ec1385-9d52-471d-8fbf-e1fbcec6c6ca` with `retry_budget_cycles: 3`
- merge-to-main still remains: integrate the latest `origin/main`, rerun the repo gates, replay from merged main if required for protected truth updates, and only then update `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml`

## Notes For The Next Assistant

- keep selector coverage unambiguous; the catalog is designed to fail validation on overlap so new workflows must be assigned deliberately
- treat `config/correction-loops.json` as the canonical contract, not the wrapper output or receipt schema
- if the Windmill replay succeeds before the final main merge, record that in the ADR and receipt but still leave protected integration files for the merged-main step
