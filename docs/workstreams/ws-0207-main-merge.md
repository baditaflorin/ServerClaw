# Workstream WS-0207 Main Merge

- ADR: [ADR 0207](../adr/0207-anti-corruption-layers-at-provider-boundaries.md)
- Title: Integrate the verified ADR 0207 live apply into `origin/main`
- Status: ready
- Branch: `codex/ws-0207-main-recut`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0207-main-recut`
- Owner: codex
- Depends On: `ws-0207-live-apply`

## Scope

- merge the finished ADR 0207 provider-boundary refactor onto the latest `origin/main`
- refresh the workstream registry, ADR metadata, receipts, and release-facing truth surfaces on the merged tree
- prove the integrated branch through local validation, build-server `remote-validate`, worker post-merge gate replay, and a governed live Hetzner DNS reconcile

## Verification

- release candidate prep in progress on `codex/ws-0207-main-recut`
