# Workstream ws-0193-main-merge

- ADR: [ADR 0193](../adr/0193-plane-kanban-task-board.md)
- Title: Integrate ADR 0193 live apply into `origin/main`
- Status: live_applied
- Branch: `codex/ws-0193-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0193-main-merge`
- Owner: codex
- Depends On: `ws-0193-live-apply`
- Conflicts With: none

## Purpose

Carry the verified ADR 0193 Plane live-apply branch into the latest `origin/main`, apply the protected integration files from mainline truth, rerun the mainline validation path, and push the merge only after the live apply is replayed from merged main.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0193-main-merge.md`
- `README.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `docs/adr/0193-plane-kanban-task-board.md`
- `docs/workstreams/adr-0193-plane-kanban-task-board.md`
- `receipts/live-applies/2026-03-27-adr-0193-plane-live-apply.json`
- `build/platform-manifest.json`

## Plan

- stage and validate the resolved ADR 0193 integration tree
- replay the Plane live apply from mainline truth
- update protected main-only state after the live replay is verified
- push the final merge into `origin/main`

## Outcome

- latest `origin/main` was fetched and merged before the final Plane replay
- the merged-main candidate kept the Plane replay-safe topology defaults that now resolve controller URLs from `hostvars['proxmox_florin'].platform_service_topology`
- `make live-apply-service service=plane env=production ALLOW_IN_PLACE_MUTATION=true` reconverged the Plane host, database, runtime, bootstrap, and ADR-sync lanes from the merged-main candidate
- the shared public edge lane was then completed with `make configure-edge-publication env=production` after regenerating the required portal/docs publication artifacts
- the final live evidence is recorded in `receipts/live-applies/2026-03-28-adr-0193-plane-mainline-live-apply.json`
