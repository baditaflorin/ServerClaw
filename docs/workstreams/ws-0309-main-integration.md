# Workstream ws-0309-main-integration: Integrate ADR 0309 Onto `main`

- ADR: [ADR 0309](../adr/0309-task-oriented-information-architecture-across-the-platform-workbench.md)
- Title: Carry the task-oriented ops-portal information architecture onto exact mainline truth and replay it from `main`
- Status: in_progress
- Branch: `codex/ws-0309-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0309-main-integration`
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
  release/docs artifacts, generated platform vars, and ADR metadata
- rerun the full validation path from the integrated tree
- perform the production `ops_portal` replay from this exact-main candidate
- push the resulting `main` branch once the integrated replay is verified

## Initial State

- current `origin/main` baseline before the merge: `5f93f0cf809ffcc755a41be2678e76350933ed37`
- current repo version before integration: `0.177.139`
- current platform version before integration: `0.130.87`
- source workstream evidence already records the blocked branch replay in
  `receipts/live-applies/evidence/2026-04-02-ws-0309-branch-live-apply.txt`

## Verification Plan

- refresh release metadata from the integrated tree
- rerun the branch-safe portal checks plus the protected generated-docs path
- run the broader repo automation path from the integration branch
- replay `make live-apply-service service=ops_portal env=production` from this
  exact-main checkout
- verify the live portal root page and lane shell cues over the guest-local
  runtime after the replay
