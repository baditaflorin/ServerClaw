# Workstream ws-0228-main-merge

- ADR: [ADR 0228](../adr/0228-windmill-as-the-default-browser-and-api-operations-surface.md)
- Title: Integrate ADR 0228 live apply into `origin/main`
- Status: in_progress
- Included In Repo Version: 0.177.64
- Platform Version Observed During Merge: 0.130.45
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
- `docs/release-notes/0.177.64.md`
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

- latest `origin/main` through commit `7c71a5c8` is merged into this worktree branch, and the Windmill conflict surface is resolved with the live-proved hash-backed seeded-script execution path plus stale worker-empty-directory pruning
- release `0.177.64` is already prepared on this branch with ADR 0228 as the only new canonical changelog entry, while the current platform baseline still reads `0.130.45`
- the remaining steps before push are the exact-main Windmill replay, the final ADR/workstream/receipt updates, the `platform_version` bump to `0.130.46`, and the post-merge/server-resident reconciliation verification
