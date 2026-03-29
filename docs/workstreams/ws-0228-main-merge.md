# Workstream ws-0228-main-merge

- ADR: [ADR 0228](../adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md)
- Title: Integrate ADR 0228 live apply into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.70
- Platform Version Observed During Merge: 0.130.48
- Release Date: 2026-03-29
- Branch: `codex/ws-0228-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0228-main-merge`
- Owner: codex
- Depends On: `ws-0228-live-apply`
- Conflicts With: none

## Purpose

Carry the verified ADR 0228 live-apply evidence onto the latest `origin/main`,
cut the protected release and canonical-truth files from that merged candidate,
replay the live Windmill convergence from the current mainline, and push the
fully integrated result to `origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0228-main-merge.md`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.70.md`
- `versions/stack.yaml`
- `README.md`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md`
- `docs/workstreams/ws-0228-live-apply.md`
- `docs/runbooks/windmill-default-operations-surface.md`
- `docs/adr/.index.yaml`
- `receipts/live-applies/2026-03-28-adr-0228-windmill-default-operations-surface-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0228-windmill-default-operations-surface-mainline-live-apply.json`

## Plan

- merge the published `codex/ws-0228-live-apply` branch into a fresh worktree created from latest `origin/main`
- replay `make converge-windmill` from the merged current-main candidate and refresh the live Windmill API evidence on that exact integrated codebase
- cut the next patch release, refresh the protected canonical-truth surfaces, and update ADR 0228 metadata with the official first merged repo version and current platform version
- rerun the release/canonical-truth validation gates and push the integrated result to `origin/main`

## Current State

- latest `origin/main` through commit `414c0b27` is merged into this worktree branch, including the intervening ADR 0248 session-authority mainline release surfaces on top of the earlier ADR 0252 route-and-DNS publication replay
- the current merged candidate keeps the exact-head Windmill fixes that stage raw apps through a `.gitignore`-aware controller-local mirror, preserve the synchronized operator admin lockfile, and prune stale worker directories before the worker-safe validation fallback runs
- the integrated release target for ADR 0228 is now repository version `0.177.70`; the remaining execution step is the final exact-head Windmill replay plus representative API proof refresh before pushing this merged result to `origin/main`
