# Workstream ws-0205-main-final

- ADR: [ADR 0205](../adr/0205-capability-contracts-before-product-selection.md)
- Title: Integrate ADR 0205 live apply into `origin/main`
- Status: ready
- Branch: `codex/ws-0205-main-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0205-main-final`
- Owner: codex
- Depends On: `ws-0205-live-apply`
- Conflicts With: none

## Purpose

Carry the finished ADR 0205 capability-contract implementation onto the latest
`origin/main`, replay the `ops_portal` live apply from the merged candidate,
and refresh the protected integration truth only after the merged-main replay
is verified end to end.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0205-main-final.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/0205-capability-contracts-before-product-selection.md`
- `docs/workstreams/adr-0205-capability-contracts-before-product-selection.md`
- `docs/adr/.index.yaml`
- `config/capability-contract-catalog.json`
- `scripts/capability_contracts.py`
- `scripts/platform_manifest.py`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/templates/partials/overview.html`
- `receipts/live-applies/2026-03-28-adr-0205-capability-contracts-before-product-selection*.json`

## Plan

- rebase the ADR 0205 implementation onto the latest `origin/main`
- validate the capability-contract catalog, platform manifest, and ops-portal regression slice
- replay `ops_portal` from the merged candidate and verify the live capability-contract panel
- update ADR metadata, release truth, receipts, and generated artifacts only after the live replay passes
