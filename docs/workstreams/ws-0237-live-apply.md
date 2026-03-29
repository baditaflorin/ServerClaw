# Workstream WS-0237: Schema-First Human Forms Live Apply

- ADR: [ADR 0237](../adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md)
- Title: Live apply schema-first Windmill operator admin forms via React Hook Form and Zod
- Status: live_applied
- Implemented In Repo Version: 0.177.74
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0237-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0237-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding-and-offboarding`, `adr-0122-windmill-operator-access-admin`
- Conflicts With: none
- Shared Surfaces: `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`, `tests/test_windmill_operator_admin_app.py`, `docs/runbooks/windmill-operator-access-admin.md`, `docs/runbooks/configure-windmill.md`, `docs/adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md`, `docs/adr/.index.yaml`, `docs/workstreams/ws-0237-live-apply.md`, `workstreams.yaml`, `receipts/live-applies/2026-03-28-adr-0237-schema-first-human-forms-live-apply.json`

## Scope

- migrate the Windmill operator access admin raw app from hand-managed React state to schema-first forms backed by React Hook Form and Zod
- commit the frontend dependency lockfile and make the Windmill runtime install raw-app frontend dependencies before `wmill sync push`
- replay `make converge-windmill` from the rebased latest-`origin/main` worktree and verify the deployed app plus a live backend workflow on `docker-runtime-lv3`
- record enough branch-local evidence for a safe protected-file follow-up on `main`

## Expected Repo Surfaces

- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/App.tsx`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/index.css`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/schemas.ts`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `tests/test_windmill_operator_admin_app.py`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/configure-windmill.md`
- `docs/adr/0237-schema-first-human-forms-via-react-hook-form-and-zod.md`
- `docs/adr/.index.yaml`
- `docs/workstreams/ws-0237-live-apply.md`
- `receipts/live-applies/2026-03-28-adr-0237-schema-first-human-forms-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- Windmill app `f/lv3/operator_access_admin` exposes the schema-first raw-app bundle, including `/schemas.ts`
- the live app still points at the governed operator-management runnables used by ADR 0108 and ADR 0122
- the Windmill runtime installs frontend dependencies inside the seed app sync directory before raw-app sync so schema-first dependencies bundle cleanly during live applies

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py -q` returned `9 passed in 0.44s`
- `python3 -m py_compile config/windmill/scripts/operator-roster.py config/windmill/scripts/operator-inventory.py` passed
- `tmpdir=$(mktemp -d) && rsync -a config/windmill/apps/f/lv3/operator_access_admin.raw_app/ "$tmpdir"/ && cd "$tmpdir" && if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-package-lock --no-audit --no-fund; fi && npx tsc --noEmit` passed
- `make syntax-check-windmill` passed from the rebased latest-`origin/main` worktree
- `make converge-windmill` completed successfully with final recap `docker-runtime-lv3 ok=229 changed=39 failed=0`, `postgres-lv3 ok=63 changed=1 failed=0`, and `proxmox_florin ok=36 changed=4 failed=0`
- guest-local Windmill API verification on `docker-runtime-lv3` returned `CE v1.662.0`, `superadmin_secret@windmill.dev`, app path `f/lv3/operator_access_admin`, file list including `/schemas.ts`, and runnables `create_operator`, `list_operators`, `offboard_operator`, `operator_inventory`, `sync_operators`, and `update_operator_notes`
- guest-local `jobs/run_wait_result` for `f/lv3/operator_roster` returned `status=ok`, `operator_count=1`, `active_count=1`, and `first_operator_id=florin-badita`
- `./scripts/validate_repo.sh workstream-surfaces agent-standards` should pass after the branch-local workstream registration and ADR index refresh are committed

## Live Apply Outcome

- the first rebased replay exposed the real automation gap for ADR 0237: `Sync repo-managed Windmill raw apps` failed because the raw app bundler could not resolve `@hookform/resolvers/zod`, `react-hook-form`, or `zod`
- the runtime role now installs raw-app frontend dependencies from the synced app directory before `wmill sync push`, using `npm ci` when `package-lock.json` is present
- the clean replay from commit `51fbce93787e67eb493ed15fe5689a6283c59ae1` applied the schema-first app live without bundling failures and left the seeded healthcheck plus validation-gate status probes green
- live API verification confirmed the deployed app exposes `/schemas.ts`, preserves the expected operator-management runnables, and still drives the repo-managed roster workflow successfully

## Live Evidence

- receipt: `receipts/live-applies/2026-03-28-adr-0237-schema-first-human-forms-live-apply.json`
- syntax check: `receipts/live-applies/evidence/2026-03-28-adr-0237-syntax-check-windmill-rebased.txt`
- successful converge replay: `receipts/live-applies/evidence/2026-03-28-adr-0237-converge-windmill-retry2.txt`
- Windmill version: `receipts/live-applies/evidence/2026-03-28-adr-0237-windmill-version.txt`
- Windmill whoami: `receipts/live-applies/evidence/2026-03-28-adr-0237-windmill-whoami.txt`
- app probe: `receipts/live-applies/evidence/2026-03-28-adr-0237-operator-access-admin-app.txt`
- roster probe: `receipts/live-applies/evidence/2026-03-28-adr-0237-operator-roster.txt`
- repo validations: `receipts/live-applies/evidence/2026-03-28-adr-0237-repo-validations.txt`

## Mainline Integration

- release `0.177.74` now carries this workstream onto `origin/main`
- the later ADR 0241 and ADR 0228 receipts remain the canonical latest live evidence for the shared `operator_access` and `windmill` surfaces, so this workstream keeps its first-live proof but does not replace those top-level receipt pointers

## Merge-To-Main Notes

- completed by `ws-0237-main-merge` in release `0.177.74`
