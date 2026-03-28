# Workstream ws-0233-main-merge

- ADR: [ADR 0233](../adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md)
- Title: Integrate ADR 0233 signed release bundles into `origin/main`
- Status: in_progress
- Included In Repo Version: N/A
- Platform Version Observed During Merge: 0.130.42
- Release Date: N/A
- Branch: `codex/ws-0233-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0233-main-merge`
- Owner: codex
- Depends On: `ws-0233-live-apply`

## Purpose

Carry the verified ADR 0233 bundle-signing implementation onto the latest
`origin/main`, replay the live Gitea release-bundle path from the merged-main
candidate, refresh the protected canonical-truth surfaces for the follow-on
release cut, and push the integrated result to `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0233-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.50.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/signed-release-bundles.md`
- `docs/workstreams/ws-0233-live-apply.md`
- `.config-locations.yaml`
- `.gitea/workflows/release-bundle.yml`
- `keys/gitea-release-bundle-cosign.pub`
- `scripts/release_bundle.py`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `tests/test_release_bundle.py`
- `tests/test_gitea_runtime_role.py`
- `receipts/live-applies/2026-03-28-adr-0233-signed-release-bundles-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0233-signed-release-bundles-mainline-live-apply.json`

## Plan

- finish merging the `ws-0233-live-apply` branch onto `origin/main@7161c2df`
- replay the live Gitea bundle publishing and verification path from this
  merged-main candidate
- cut the next repository release, update the protected canonical-truth files,
  and record both the isolated live-apply and merged-main receipts

## Verification

- pending merged-main replay

## Outcome

- pending integration
