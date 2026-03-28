# Workstream WS-0238: Data-Dense Operator Grids Live Apply

- ADR: [ADR 0238](../adr/0238-data-dense-operator-grids-via-ag-grid-community.md)
- Title: Live apply AG Grid Community on the Windmill operator access roster
- Status: in_progress
- Implemented In Repo Version: pending
- Live Applied In Platform Version: pending
- Implemented On: pending
- Live Applied On: pending
- Branch: `codex/ws-0238-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0238-live-apply`
- Owner: codex
- Depends On: `adr-0108-operator-onboarding`, `adr-0122-operator-access-admin`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`, `docs/workstreams/ws-0238-live-apply.md`, `docs/adr/.index.yaml`, `docs/runbooks/windmill-operator-access-admin.md`, `config/windmill/apps/f/lv3/operator_access_admin.raw_app/*`, `tests/test_windmill_operator_admin_app.py`, `receipts/live-applies/2026-03-28-adr-0238-operator-grid-live-apply.json`, `workstreams.yaml`

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
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package.json`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/package-lock.json`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`
- `docs/workstreams/ws-0238-live-apply.md`
- `docs/adr/.index.yaml`
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

- `uv run --with pytest --with pyyaml python -m pytest tests/test_windmill_operator_admin_app.py -q`
- `ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/windmill.yml --syntax-check`
- `./scripts/validate_repo.sh agent-standards`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`
- `tmpdir="$(mktemp -d)" && mkdir -p "$tmpdir/f/lv3" && rsync -a config/windmill/apps/f/lv3/operator_access_admin.raw_app/ "$tmpdir/f/lv3/operator_access_admin.raw_app/" && cd "$tmpdir/f/lv3/operator_access_admin.raw_app" && npm ci && npx tsc --noEmit`
- `make converge-windmill`
- `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/apps/get/p/f/lv3/operator_access_admin`
- `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Foperator_roster`

## Protected Integration Files Deferred

- `VERSION`
- `changelog.md`
- top-level `README.md`
- `versions/stack.yaml`
- `docs/release-notes/*`
- `build/platform-manifest.json`

## Merge-To-Main Notes

- pending live apply and verification
