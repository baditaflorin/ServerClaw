# Workstream WS-0238: Data-Dense Operator Grids Live Apply

- ADR: [ADR 0238](../adr/0238-data-dense-operator-grids-via-ag-grid-community.md)
- Title: Live apply AG Grid Community on the Windmill operator access roster
- Status: live_applied
- Implemented In Repo Version: 0.177.63
- Live Applied In Platform Version: 0.130.45
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0238-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0238-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding`, `adr-0122-operator-access-admin`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`, `docs/workstreams/ws-0238-live-apply.md`, `docs/adr/.index.yaml`, `docs/runbooks/{budgeted-workflow-scheduler.md,config-merge-protocol.md,configure-windmill.md,service-dependency-graph-runtime.md,windmill-operator-access-admin.md}`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/{defaults/main.yml,meta/argument_specs.yml,tasks/main.yml}`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `platform/scheduler/{__init__.py,scheduler.py,windmill_client.py}`, `platform/use_cases/runbooks.py`, `scripts/{sync_windmill_seed_schedules.py,windmill_run_wait_result.py}`, `tests/{test_config_merge_windmill.py,test_windmill_circuit_clients.py,test_windmill_operator_admin_app.py}`, `receipts/live-applies/2026-03-28-adr-0238-operator-grid-live-apply.json`, `workstreams.yaml`

## Scope

- replace the hand-built Windmill operator roster table with AG Grid Community
- preserve the governed ADR 0108 and ADR 0122 backend path so only the dense
  operator view changes
- validate the raw app bundle with repo tests and a real TypeScript dependency
  install plus compile pass
- converge Windmill from this isolated worktree so the worker mirror and raw
  app seed reflect the branch under test, not the shared checkout
- capture branch-local live evidence and merge guidance without touching
  protected integration files until the final mainline step

## Expected Repo Surfaces

- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/.gitignore`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `platform/scheduler/__init__.py`
- `platform/scheduler/scheduler.py`
- `platform/scheduler/windmill_client.py`
- `platform/use_cases/runbooks.py`
- `scripts/windmill_run_wait_result.py`
- `scripts/sync_windmill_seed_schedules.py`
- `docs/runbooks/budgeted-workflow-scheduler.md`
- `docs/runbooks/config-merge-protocol.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/service-dependency-graph-runtime.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`
- `docs/workstreams/ws-0238-live-apply.md`
- `docs/adr/.index.yaml`
- `tests/test_config_merge_windmill.py`
- `tests/test_windmill_circuit_clients.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0238-operator-grid-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill workspace `lv3` serves `f/lv3/operator_access_admin` with an AG
  Grid Community roster instead of the earlier hand-built HTML table
- the roster supports quick filter, pagination, sortable and resizable columns,
  row selection by click or keyboard, and hidden metadata columns for denser
  operator review
- the selected row still drives the governed inventory lookup and off-boarding
  form without introducing a second access-management backend path

## Verification

- `uv run --with-requirements requirements/api-gateway.txt --with pytest python -m pytest tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py tests/test_windmill_circuit_clients.py tests/test_runbook_use_cases.py tests/test_world_state_repo_surfaces.py tests/test_api_gateway.py -q` passed with `75 passed in 5.21s`.
- `python3 -m py_compile platform/scheduler/__init__.py platform/scheduler/windmill_client.py platform/scheduler/scheduler.py scripts/windmill_run_wait_result.py` passed.
- `tmpdir="$(mktemp -d)" && mkdir -p "$tmpdir/f/lv3" && rsync -a config/windmill/apps/f/lv3/operator_access_admin.raw_app/ "$tmpdir/f/lv3/operator_access_admin.raw_app/" && cd "$tmpdir/f/lv3/operator_access_admin.raw_app" && npm ci && npx tsc --noEmit` passed with a clean raw-app dependency install and TypeScript compile.
- `make syntax-check-windmill`, `make preflight WORKFLOW=converge-windmill`, and `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs ansible-syntax data-models` all passed from this worktree after the ws-0238 ownership manifest was expanded to cover the helper, scheduler, runbook, and test surfaces touched during the live apply.
- `make converge-windmill` completed successfully from `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0238-live-apply` with `docker-runtime-lv3 : ok=234 changed=46 failed=0`, `postgres-lv3 : ok=63 changed=1 failed=0`, and `proxmox_florin : ok=36 changed=4 failed=0`.
- `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell -a 'docker compose --file /opt/windmill/docker-compose.yml ps' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` showed `windmill_server`, `windmill_extra`, `windmill_worker`, and `windmill_worker_native` all `Up`, with `windmill-openbao-agent` `healthy`.
- `python3 scripts/windmill_run_wait_result.py --base-url http://100.64.0.1:8005 --workspace lv3 --path f/lv3/windmill_healthcheck --payload-json '{"probe":"plain-python-verify"}'` returned the expected healthcheck payload, and `python3 scripts/windmill_run_wait_result.py --base-url http://100.64.0.1:8005 --workspace lv3 --path f/lv3/operator_roster --payload-json '{}'` returned `status: ok` with `operator_count: 1`.
- `GET /api/w/lv3/apps/get/p/f/lv3/operator_access_admin` returned `/App.tsx` and `/index.css` payloads whose SHA-256 digests exactly matched the repo worktree, proving the live raw app now follows the isolated branch checkout.
- `GET /api/w/lv3/schedules/get/f/lv3/scheduler_watchdog_loop_every_10s` and `GET /api/w/lv3/schedules/get/f/lv3/world_state/refresh_container_inventory_every_minute` both returned `enabled: true`, `is_flow: false`, the expected `script_path`, and the repo-managed summary/description plus corrected runtime `dsn` args for the container-inventory refresh schedule.

## Outcome

- ADR 0238 is live on the Windmill operator access admin surface with AG Grid Community replacing the earlier hand-built roster table while preserving the governed ADR 0108 and ADR 0122 backend paths.
- The live apply repaired a stale-source bug in the raw-app seed path: the guest-side app staging root now follows the same dedicated worktree used for the worker checkout, so isolated branch replays stop pulling older app bundles from a shared checkout.
- The live apply also hardened the Windmill raw-app automation path by retrying transient guest-side Docker EOFs during `npm ci` and `wmill sync push`, and by keeping the schedule helper responsible for converging both `enabled` state and late-arriving script targets.
- The follow-up verification fixed the controller-side helper contract too: `scripts/windmill_run_wait_result.py` now works under plain `python3`, submits by script path, falls back to script hash when needed, and polls `jobs_u/get/<job_id>` until the workflow reaches a terminal state.

## Protected Integration Files Deferred

- `VERSION`
- `changelog.md`
- top-level `README.md`
- `versions/stack.yaml`
- `docs/release-notes/*`
- `build/platform-manifest.json`

## Merge-To-Main Notes

- Protected integration files still need the latest-main merge step: `VERSION`, `changelog.md`, top-level `README.md`, `versions/stack.yaml`, `docs/release-notes/*`, and `build/platform-manifest.json`.
- Rebase this workstream on the latest `origin/main` before the integration commit, then carry the live receipt and verification summary onto the protected release surfaces without rewriting unrelated concurrent work.
- The branch-local live receipt should also note that `f/lv3/scheduler_watchdog_loop_every_10s` was corrected once through the Windmill API before the helper fix landed, and that a one-time manual probe temporarily wrote placeholder values onto `f/lv3/world_state/refresh_container_inventory_every_minute` before the successful converge restored the repo-managed schedule contract.
