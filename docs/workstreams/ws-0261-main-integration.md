# Workstream ws-0261-main-integration

- ADR: [ADR 0261](../adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md)
- Title: Integrate ADR 0261 and ADR 0262 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Included In Repo Version: 0.177.95
- Platform Version Observed During Integration: 0.130.63
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0261-main-promote`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0261-main-promote`
- Owner: codex
- Depends On: `ws-0261-live-apply`, `ws-0262-live-apply`

## Purpose

Carry the verified ADR 0261 and ADR 0262 exact-main replay onto the newest
available `origin/main`, refresh the protected release and canonical-truth
surfaces for repository version `0.177.95`, and re-validate the repo
automation plus the governed browser-runner and delegated-authz runtime proofs
before the final push to `origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0261-main-integration.md`
- `docs/workstreams/ws-0261-live-apply.md`
- `docs/workstreams/ws-0262-live-apply.md`
- `docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md`
- `docs/adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.95.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/tasks/sync_tree.yml`
- `tests/test_api_gateway_runtime_role.py`
- `receipts/live-applies/2026-03-30-adr-0261-playwright-browser-runners-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0262-openfga-keycloak-exact-main-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0261-0262-release-0.177.95-*`

## Verification

- pending final canonical-truth regeneration, repo validation sweep, and
  `git push origin HEAD:main`

## Outcome

- pending final validation and push to `origin/main`
