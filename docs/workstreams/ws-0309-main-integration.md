# Workstream ws-0309-main-integration: Integrate ADR 0309 Onto `main`

- ADR: [ADR 0309](../adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md)
- Title: Carry the task-oriented ops-portal information architecture onto exact mainline truth and replay it from `main`
- Status: live_applied
- Included In Repo Version: 0.177.148
- Platform Version Observed During Integration: 0.130.93
- Release Date: 2026-04-03
- Live Applied On: 2026-04-03
- Branch: `codex/ws-0309-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0309-main-integration`
- Source Branch: `codex/ws-0309-live-apply`
- Owner: codex

## Purpose

Finish the ADR 0309 rollout from the exact mainline candidate after the
branch-local workstream proved the implementation and validation surfaces but
the governed branch replay stopped at the protected canonical-truth refresh.

## Summary

- merge `codex/ws-0309-live-apply` onto the latest `origin/main`
- refresh the protected integration files in the correct place:
  `README.md`, `VERSION`, `changelog.md`, `versions/stack.yaml`, generated
  release/docs artifacts, release-note generator surfaces, generated platform
  vars, and ADR metadata
- rerun the full validation path from the integrated tree
- perform the production `ops_portal` replay from this exact-main candidate
- push the resulting `main` branch once the integrated replay is verified

## Initial State

- exact `origin/main` baseline before the final merge: `9c58e76c652b9d5e65504d44412aad454207bcb8`
- repo version before the final integration cut: `0.177.147`
- platform version before the final mainline replay: `0.130.92`
- source workstream evidence already recorded the blocked branch replay in
  `receipts/live-applies/evidence/2026-04-02-ws-0309-branch-live-apply.txt`

## Outcome

- merged the ws-0309 branch onto the latest `origin/main`, resolved the
  overlapping ADR 0310 and ADR 0312 `ops_portal` surfaces, and cut release
  `0.177.148`
- verified the live `ops_portal` runtime on `docker-runtime` with
  guest-local health checks, lane/help marker assertions, deployed file checks,
  container inspection, and edge-auth redirect verification
- recorded the recovery loop where the first exact-main replay failed on a
  worktree-local SSH key path, the second replay stalled after the service
  converge, and the post-apply restic trigger initially failed because the
  guest-local OpenBao API had become sealed
- recovered that sealed-state drift with a narrow repo-managed unseal replay,
  reran the restic trigger successfully, and advanced the live platform lineage
  to `0.130.93`
- after the exact-main replay completed, `origin/main` advanced to
  `ef412b0f061517b64920b7328102e23b89b0774d` with repo-local operator-tool
  scripts only; the final closeout can absorb that commit without changing the
  already-verified deployed `ops_portal` payload or platform lineage

## Remaining Work

- none; this workstream is ready to merge to local `main`, push to
  `origin/main`, release its locks, and remove the temporary integration
  worktree
