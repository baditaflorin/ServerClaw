# Mainline release-scratchpad backfill

- ADR: 0174
- Status: merged; release bookkeeping remains pending until the next version cut
- Date: 2026-10-13

## Purpose

The canonical changelog generator derives `## Unreleased` entries from
workstream metadata. Three post-0.179.51 changes were already merged and had
accurate changelog bullets, but no workstream records. As a result,
`canonical_truth.py --check` treated those bullets as stale and would delete
them. These merged, unreleased records preserve the existing release notes
until the next version cut while making their source explicit.

## Source evidence

- `ws-0525` and `ws-0526`: commit `59ae3dbe2`, PR #336, merged from
  `fleet/hardening-2026-10-13` on 2026-10-13. The commit covers the build-broker
  PKI renewal fix, stale socket-activated proxy unit state, and the VM template's
  unused OpenIPMI service.
- `ws-0527`: commit `a667dc3fe` on main. It adds log rotation to the public-edge
  NGINX role. The original source branch was not recorded.

The worktree paths recorded in these entries refer to this mainline metadata
backfill; the original implementation worktrees were not retained. These
records preserve release notes only. They do not assert that every change in
those commits was fully applied to the live platform.
