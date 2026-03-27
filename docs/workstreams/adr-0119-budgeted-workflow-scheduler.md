# Workstream ADR 0119: Budgeted Workflow Scheduler

- ADR: [ADR 0119](../adr/0119-budgeted-workflow-scheduler.md)
- Title: Orchestration layer between the goal compiler and Windmill — enforces hard per-workflow budgets (duration, steps, concurrency, host count, restart depth) and terminates or escalates on violation
- Status: live_applied
- Implemented In Repo Version: 0.177.10
- Live Applied In Platform Version: 0.130.30
- Implemented On: 2026-03-27
- Live Applied On: 2026-03-27
- Branch: `codex/ws-0119-main-final`
- Worktree: `.worktrees/ws-0119-main-final`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0048-command-catalog`, `adr-0058-nats-event-bus`, `adr-0071-agent-observation-loop`, `adr-0098-postgres-ha`, `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`, `adr-0116-change-risk-scoring`
- Conflicts With: `adr-0112-goal-compiler` (shared workflow submission path)
- Shared Surfaces: `platform/scheduler/`, `config/workflow-catalog.json` (budget block additions), `config/workflow-defaults.yaml`, Postgres advisory locks

## Scope

- create `platform/scheduler/__init__.py`
- create `platform/scheduler/scheduler.py` — `BudgetedWorkflowScheduler.submit()`: loads budget from catalog, acquires Postgres advisory lock, checks concurrency, submits to Windmill, starts watchdog
- create `platform/scheduler/budgets.py` — budget loader from `config/workflow-catalog.json`; merge with defaults from `config/workflow-defaults.yaml`
- create `platform/scheduler/watchdog.py` — `Watchdog.monitor()`: polls active Windmill jobs every 30 seconds; cancels and escalates on duration or step violation
- create `platform/scheduler/rollback_guard.py` — `RollbackGuard.check_depth()`: walks `ledger.events` chain by `actor_intent_id` to count rollback depth
- create `config/workflow-defaults.yaml` — default budget values from ADR 0119
- extend `config/workflow-catalog.json` — add `budget` block to all existing workflow entries (use defaults for those without explicit requirements; add explicit budgets for known long-running workflows like Packer builds)
- create `windmill/scheduler/watchdog-loop.py` — Windmill workflow running on a 30-second schedule; calls `Watchdog.monitor()`; posts budget violation events to NATS and ledger
- update `lv3 run` CLI command submission path — call `BudgetedWorkflowScheduler.submit(intent)` instead of Windmill API directly
- write `tests/unit/test_scheduler_budgets.py` — test budget loading, default merging, concurrency lock, rollback depth guard

## Non-Goals

- Changing Windmill's internal step execution — budgets are enforced externally by the watchdog, not inside Windmill
- Rate limiting read-only diagnostic workflows — budgets apply only to `execution_class: mutation` workflows

## Expected Repo Surfaces

- `platform/scheduler/__init__.py`
- `platform/scheduler/scheduler.py`
- `platform/scheduler/budgets.py`
- `platform/scheduler/watchdog.py`
- `platform/scheduler/rollback_guard.py`
- `config/workflow-defaults.yaml`
- `config/workflow-catalog.json` (patched: budget blocks added)
- `windmill/scheduler/watchdog-loop.py`
- `docs/runbooks/budgeted-workflow-scheduler.md`
- `docs/adr/0119-budgeted-workflow-scheduler.md`
- `docs/workstreams/adr-0119-budgeted-workflow-scheduler.md`

## Expected Live Surfaces

- `lv3 run "deploy netbox"` routes through the scheduler; the Windmill job is submitted with a budget attached
- Running two simultaneous `lv3 run "deploy netbox"` commands results in one `CONCURRENCY_LIMIT` rejection
- A manually crafted long-running test workflow (sleep > max_duration_seconds) is cancelled by the watchdog within 30 seconds of the timeout
- Budget violation events appear in `ledger.events` with `event_type: execution.budget_exceeded`

## Verification

- Run `pytest tests/unit/test_scheduler_budgets.py -v` → all tests pass
- Submit a test workflow with `max_duration_seconds: 10` that sleeps for 20 seconds; confirm Windmill job is cancelled and a `execution.budget_exceeded` ledger event is written
- Attempt two simultaneous `converge-netbox` submissions; confirm the second returns `CONCURRENCY_LIMIT`
- Confirm rollback depth guard blocks a rollback-of-rollback chain beyond depth 1

## Live Apply Evidence

- 2026-03-27 latest-main live apply replayed `playbooks/windmill.yml` successfully from the rebased integration worktree with `docker-runtime-lv3 : ok=216 changed=38 failed=0`.
- The live Windmill script bodies for `f/lv3/intent_queue_dispatcher`, `f/lv3/lane_scheduler`, `f/lv3/scheduler_watchdog`, and `f/lv3/scheduler_watchdog_loop` were rechecked through the API and matched the branch-local sources byte-for-byte after apply.
- Manual end-to-end `jobs/run_wait_result` verification succeeded for `f/lv3/windmill_healthcheck`, `f/lv3/intent_queue_dispatcher`, `f/lv3/lane_scheduler`, `f/lv3/scheduler_watchdog`, and `f/lv3/scheduler_watchdog_loop`.
- The repo-managed schedules `f/lv3/intent_queue_dispatcher_every_minute`, `f/lv3/lane_scheduler_every_2s`, `f/lv3/scheduler_watchdog_every_30s`, and `f/lv3/scheduler_watchdog_loop_every_10s` were verified as enabled after apply.
- The latest-main replay removed the duplicate `f/lv3/scheduler_watchdog_loop` seed contract from the Windmill defaults, so the wrapper path is now stable and no longer overwritten by the watchdog implementation body during sync.
- The live worker runtime env on `docker-runtime-lv3` now exposes `LV3_WINDMILL_BASE_URL` and `LV3_WINDMILL_TOKEN`, and `/srv/proxmox_florin_server/.local/windmill/superadmin-secret.txt` exists on the worker checkout.

## Repo Validation

- `uv run --with pytest python -m pytest -q tests/test_config_merge_repo_surfaces.py tests/test_config_merge_windmill.py tests/test_windmill_operator_admin_app.py tests/test_windmill_circuit_clients.py` → passed (`47 passed`)
- `python3 -m py_compile scripts/sync_windmill_seed_scripts.py scripts/windmill_run_wait_result.py platform/scheduler/scheduler.py` → passed
- `ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check` → passed
- `uvx --from ansible-lint ansible-lint collections/ansible_collections/lv3/platform/roles/windmill_runtime` → passed with non-fatal warnings only

## Final Integration State

- This workstream is now live-applied from the latest `main`.
- The mainline release that records the verified state is repository version `0.177.10` with platform version `0.130.30`.
- The durable receipt for the successful latest-main replay is `receipts/live-applies/2026-03-27-adr-0119-budgeted-workflow-scheduler-mainline-live-apply.json`.
- No additional merge-to-main cleanup is required for ADR 0119 beyond the normal push of this mainline release.

## Merge Criteria

- Unit tests pass
- Duration budget enforcement verified with test workflow
- Concurrency lock verified
- Rollback depth guard tested manually
- Budget blocks added to all workflows in `config/workflow-catalog.json`

## Notes For The Next Assistant

- Postgres advisory locks are session-scoped by default; use `pg_try_advisory_xact_lock()` (transaction-scoped) instead of `pg_try_advisory_lock()` to ensure locks are released even if the scheduler process crashes
- The watchdog workflow runs every 30 seconds; ensure it has `max_concurrent_instances: 1` in its own budget block to prevent watchdog overlap
- The rollback chain walk using `actor_intent_id` requires that the goal compiler always sets `actor_intent_id` on rollback intents pointing to the original intent. Verify this is implemented before testing the rollback guard.
- For the first release, `max_touched_hosts` enforcement is advisory only (logs a warning but does not block). Promote it to a hard block in a follow-up after verifying the Ansible inventory size reporting is reliable across all playbooks.
- The latest-main replay fixed a real seed-sync regression: keep `windmill_seed_scripts` path values unique, or Windmill will silently overwrite the earlier script body during manifest replay.
