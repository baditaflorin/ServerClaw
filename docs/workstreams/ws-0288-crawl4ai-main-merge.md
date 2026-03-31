# Workstream ws-0288-crawl4ai-main-merge: ADR 0288 Crawl4AI Exact-Main Integration

- ADR: [ADR 0288](../adr/0288-crawl4ai-as-the-llm-optimised-web-content-crawler.md)
- Title: integrate the private Crawl4AI runtime onto the latest `origin/main` without disturbing the already-merged Flagsmith ws-0288 records
- Status: in_progress
- Included In Repo Version: pending
- Canonical Mainline Receipt: pending
- Live Applied In Platform Version: pending
- Branch: `codex/ws-0288-crawl4ai-main-merge-r1`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0288-crawl4ai-main-merge-r1`
- Owner: codex
- Depends On: none
- Conflicts With: `ws-0288-live-apply`, `ws-0288-main-merge`

## Naming Note

The existing `ws-0288-*` records on `origin/main` belong to the already-merged
Flagsmith ADR branch that shares the same numeric ADR identifier. This
collision-safe workstream keeps the Crawl4AI exact-main integration separate so
the registry and workstream docs stay merge-safe.

## Scope

- carry the Crawl4AI runtime, private service topology, health probes, SLOs,
  workflow metadata, image pinning, and verification surfaces onto the latest
  `origin/main`
- keep Crawl4AI off Docker's legacy default `bridge` by using a compose-managed
  bridge network and preserving the bridge-recovery hardening that was proven
  during the earlier live-apply correction loop
- record exact-main live-apply evidence and then update the protected release
  and platform truth surfaces only after the mainline replay is verified

## Current Verification

- Focused repository regression slice passed:
  `57 passed in 16.10s` across the Crawl4AI runtime, metadata, docker bridge
  helper, docker runtime role, and generated platform vars tests.
- `make syntax-check-crawl4ai` passed from this latest-main worktree.
- The exact-main live apply, protected release truth updates, and final
  merge-to-`main` still remain in flight on this workstream.
