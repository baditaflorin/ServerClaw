# Workstream ws-0254-main-merge

- ADR: [ADR 0254](../adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md)
- Title: Integrate ADR 0254 exact-main replay onto `origin/main`
- Status: `ready_for_merge`
- Included In Repo Version: pending
- Platform Version Observed During Merge: pending
- Release Date: pending
- Branch: `codex/ws-0254-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0254-main-merge`
- Owner: codex
- Depends On: `ws-0254-live-apply`

## Purpose

Carry the verified ADR 0254 latest-main replay onto the current `origin/main`,
refresh the protected release and canonical-truth surfaces from that merged
baseline, re-run the exact-main ServerClaw converge path from the integration
commit, and record the canonical mainline live-apply receipt before pushing
`origin/main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0254-main-merge.md`
- `docs/workstreams/ws-0254-live-apply.md`
- `docs/adr/0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.84.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `receipts/live-applies/2026-03-29-adr-0254-serverclaw-distinct-product-surface-mainline-live-apply.json`

## Verification

- pending release cut from the refreshed latest `origin/main`
- pending exact-main `make converge-serverclaw`
- pending public `chat.lv3.org` redirect and HTTPS checks from the merged mainline state
- pending guest-local admin sign-in and internal upstream path verification from the merged mainline state

## Outcome

- pending
