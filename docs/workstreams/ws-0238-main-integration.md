# Workstream ws-0238-main-integration

- ADR: [ADR 0238](../adr/0238-data-dense-operator-grids-via-ag-grid-community.md)
- Title: Integrate ADR 0238 operator grid into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.66
- Platform Version Observed During Merge: 0.130.46
- Release Date: 2026-03-29
- Branch: `codex/ws-0238-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0238-main-integration`
- Owner: codex
- Depends On: `ws-0238-live-apply`

## Purpose

Carry the verified ADR 0238 AG Grid Community rollout onto the latest
`origin/main` after ADR 0232 advanced the mainline to `0.177.65`, cut release
`0.177.66`, refresh the protected canonical-truth surfaces, and preserve the
existing later ADR 0241 canonical-truth ownership of the broader top-level
`windmill` and `operator_access` latest-receipt pointers.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0238-main-integration.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.66.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0238-data-dense-operator-grids-via-ag-grid-community.md`
- `docs/workstreams/ws-0238-live-apply.md`
- `docs/runbooks/budgeted-workflow-scheduler.md`
- `docs/runbooks/config-merge-protocol.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/service-dependency-graph-runtime.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/**`
- `platform/scheduler/__init__.py`
- `platform/scheduler/scheduler.py`
- `platform/scheduler/windmill_client.py`
- `platform/use_cases/runbooks.py`
- `scripts/windmill_run_wait_result.py`
- `scripts/sync_windmill_seed_schedules.py`
- `tests/test_config_merge_windmill.py`
- `tests/test_windmill_circuit_clients.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0238-operator-grid-live-apply.json`

## Verification

- `git merge --ff-only codex/ws-0238-live-apply` advanced this worktree from
  `origin/main` `0.177.65` to the latest verified ws-0238 branch tip
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0238 AG Grid operator-grid rollout while the current platform baseline remains 0.130.46" --dry-run`
  reported `Current version: 0.177.65`, `Next version: 0.177.66`, and
  `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0238 AG Grid operator-grid rollout while the current platform baseline remains 0.130.46"`
  prepared release `0.177.66`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`,
  `uv run --with pyyaml python scripts/generate_status_docs.py --write`,
  `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write`,
  and `uv run --with pyyaml python scripts/generate_diagrams.py --write`
  refreshed the protected generated surfaces for the integrated candidate

## Outcome

- release `0.177.66` carries ADR 0238 onto `main`
- the integrated platform baseline remains `0.130.46`
- the canonical branch-local live evidence remains
  `receipts/live-applies/2026-03-28-adr-0238-operator-grid-live-apply.json`
