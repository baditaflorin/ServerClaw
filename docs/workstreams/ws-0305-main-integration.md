# Workstream ws-0305-main-integration

- ADR: [ADR 0305](../adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md)
- Title: Integrate ADR 0305 k6 exact-main replay onto `origin/main`
- Status: in_progress
- Included In Repo Version: 0.177.117
- Platform Version Observed During Integration: 0.130.75
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0305-mainline-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0305-mainline-final`
- Owner: codex
- Depends On: `ws-0305-live-apply`

## Purpose

Carry the verified ADR 0305 branch-local live apply onto the synchronized
`origin/main` baseline, cut release `0.177.117` from that exact-main tree, rerun
the authoritative repository automation and k6 validation paths from committed
source, and publish one canonical mainline receipt that preserves both the
passing smoke path and the truthful non-zero live load failure.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0305-main-integration.md`
- `docs/workstreams/ws-0305-live-apply.md`
- `docs/adr/0305-k6-for-continuous-load-testing-and-slo-error-budget-burn-validation.md`
- `docs/runbooks/k6-load-testing.md`
- `docs/runbooks/configure-openfga.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/live-applies/`
- `receipts/k6/`

## Verification

- Release `0.177.117` was cut from committed source `4508722f21ff06e8da014521f35cac382b2b5dc9`.
- The first exact-main validation pass exposed three repo-integration gaps rather than live-platform regressions:
  the current branch needed its own active integration workstream, the generated
  dependency graph was stale, and `versions/stack.yaml` referenced the final
  canonical ADR 0305 receipt before that receipt had been written.
- The first full `make validate` pass also exposed four OpenBao helper
  `ansible-lint` `name[template]` violations in the unseal helper tasks after
  the latest-main merge.

## Outcome

- Integration is in progress on the dedicated exact-main branch.
- The final canonical receipt and terminal workstream status will be recorded
  here once the rerun validation bundle and committed-source k6 smoke/load
  replays complete.
