# Workstream WS-0238: Data-Dense Operator Grids Live Apply

- ADR: [ADR 0238](../adr/0238-data-dense-operator-grids-via-ag-grid-community.md)
- Title: Live apply AG Grid Community on the Windmill operator access roster
- Status: implemented
- Implemented In Repo Version: 0.177.56
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0238-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0238-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding`, `adr-0122-operator-access-admin`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`, `docs/workstreams/ws-0238-live-apply.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-windmill.md`, `docs/runbooks/windmill-operator-access-admin.md`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/{defaults/main.yml,meta/argument_specs.yml,tasks/main.yml}`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `scripts/sync_windmill_seed_schedules.py`, `tests/test_config_merge_windmill.py`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/2026-03-28-adr-0238-operator-grid-live-apply.json`, `workstreams.yaml`

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
- `scripts/sync_windmill_seed_schedules.py`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`
- `docs/workstreams/ws-0238-live-apply.md`
- `docs/adr/.index.yaml`
- `tests/test_config_merge_windmill.py`
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

- `uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py tests/test_world_state_repo_surfaces.py -q` passed with `46 passed in 6.82s`, and the focused rerun `uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py tests/test_config_merge_windmill.py -q` passed with `42 passed in 1.28s`.
- `tmpdir="$(mktemp -d)" && mkdir -p "$tmpdir/f/lv3" && rsync -a config/windmill/apps/f/lv3/operator_access_admin.raw_app/ "$tmpdir/f/lv3/operator_access_admin.raw_app/" && cd "$tmpdir/f/lv3/operator_access_admin.raw_app" && npm ci && npx tsc --noEmit` passed with a clean AG Grid raw-app dependency install and TypeScript compile.
- `make syntax-check-windmill` and `make preflight WORKFLOW=converge-windmill` both passed from this worktree.
- `./scripts/validate_repo.sh workstream-surfaces agent-standards yaml json role-argument-specs ansible-syntax data-models` now passes after the ws-0238 ownership manifest was expanded to cover the Windmill role, schedule helper, runbook, and test surfaces touched during the live apply.
- The narrowed live replay from `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0238-live-apply` completed successfully with `docker-runtime-lv3 ok=106 changed=21 failed=0` after setting `windmill_worker_checkout_repo_root_local_dir` and letting `windmill_seed_app_repo_root_local_dir` follow that same worktree root.
- Direct Windmill API verification showed `f/lv3/operator_access_admin` storing the AG Grid markers `AgGridReact`, `themeQuartz.withParams`, `quickFilterText={deferredQuickFilterText}`, and `includeHiddenColumnsInQuickFilter={true}` in `/App.tsx`.
- `POST /api/w/lv3/jobs/run_wait_result/p/f/lv3/operator_roster` returned `status: ok`, `operator_count: 1`, and the expected sanitized operator keys.
- `GET /api/w/lv3/schedules/get/f/lv3/scheduler_watchdog_loop_every_10s` and `GET /api/w/lv3/schedules/get/f/lv3/world_state/refresh_container_inventory_every_minute` both returned `enabled: true`, the repo-managed summary and description, `is_flow: false`, the expected `script_path`, and corrected runtime args for the container-inventory refresh schedule.

## Outcome

- ADR 0238 is live on the Windmill operator access admin surface with AG Grid Community replacing the earlier hand-built roster table while preserving the governed ADR 0108 and ADR 0122 backend paths.
- The live apply repaired a stale-source bug in the raw-app seed path: the guest-side app staging root now follows the same dedicated worktree used for the worker checkout, so isolated branch replays stop pulling older app bundles from a shared checkout.
- The live apply also hardened the Windmill raw-app automation path by retrying transient guest-side Docker EOFs during `npm ci` and `wmill sync push`, and by keeping the schedule helper responsible for converging both `enabled` state and late-arriving script targets.

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
