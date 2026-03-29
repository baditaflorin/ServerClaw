# Workstream WS-0244: Mainline Integration

- ADR: [ADR 0244](../adr/0244-runtime-assurance-matrix-per-service-and-environment.md)
- Title: Integrate ADR 0244 runtime assurance matrix into `origin/main`
- Status: in_progress
- Included In Repo Version: pending release bump
- Platform Version Observed During Merge: 0.130.50
- Release Date: pending exact-main verification
- Branch: `codex/ws-0244-main-merge-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0244-main-merge-r3`
- Owner: codex
- Depends On: `ws-0244-live-apply`

## Purpose

Carry the verified ADR 0244 live apply onto the latest `origin/main`, refresh
the protected canonical-truth surfaces, and preserve exact-main verification
for the authenticated API gateway plus ops portal runtime-assurance flow.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0244-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.74.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`
- `docs/adr/0244-runtime-assurance-matrix-per-service-and-environment.md`
- `docs/workstreams/ws-0244-live-apply.md`
- `docs/runbooks/runtime-assurance-matrix.md`
- `config/runtime-assurance-matrix.json`
- `docs/schema/runtime-assurance-matrix.schema.json`
- `scripts/runtime_assurance.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/app.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `tests/test_runtime_assurance.py`
- `tests/test_api_gateway.py`
- `tests/test_api_gateway_runtime_role.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `receipts/live-applies/2026-03-29-adr-0244-runtime-assurance-matrix-live-apply.json`

## Verification

- pending focused latest-main test and validation replay on `codex/ws-0244-main-merge-r3`
- pending protected-surface refresh for the next patch release
- pending exact-main runtime verification on the live platform before `origin/main` push
