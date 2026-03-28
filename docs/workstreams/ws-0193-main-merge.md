# Workstream ws-0193-main-merge

- ADR: [ADR 0193](../adr/0193-plane-kanban-task-board.md)
- Title: Integrate ADR 0193 live apply into `origin/main`
- Status: in-progress
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
