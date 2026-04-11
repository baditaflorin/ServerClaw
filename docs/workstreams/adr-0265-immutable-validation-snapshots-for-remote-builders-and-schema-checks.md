# Workstream WS-0265: Immutable Validation Snapshots For Remote Builders And Schema Checks

- ADR: [ADR 0265](../adr/0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md)
- Title: Replace mutable remote build mirrors with immutable validation snapshots
- Status: live_applied
- Implemented In Repo Version: 0.177.78
- Live Applied In Platform Version: 0.130.53
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0265-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0265-live-apply`
- Owner: codex
- Depends On: `adr-0082-remote-build-execution-gateway`, `adr-0083-docker-check-runners-for-repository-validation`, `adr-0156-agent-session-workspace-isolation`, `adr-0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md`, `docs/adr/0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md`, `docs/adr/.index.yaml`, `docs/runbooks/remote-build-gateway.md`, `docs/runbooks/validation-gate.md`, `docs/runbooks/validate-repository-automation.md`, `docs/runbooks/agent-session-workspace-isolation.md`, `scripts/remote_exec.sh`, `scripts/repository_snapshot.py`, `tests/test_remote_exec.py`, `tests/test_repository_snapshot.py`

## Scope

- replace mutable remote `rsync` mirrors and `.git-remote` worktree metadata
  shims with immutable content-addressed repository snapshots
- keep the session-scoped build-server isolation contract while adding fresh
  per-run snapshot namespaces beneath the remote session workspace
- make the remote validation path reason about repository content without
  relying on mirrored `.git` internals
- record live build-server evidence and final merge-to-main follow-up once the
  latest `origin/main` replay passes end to end

## Expected Repo Surfaces

- `scripts/remote_exec.sh`
- `scripts/repository_snapshot.py`
- `scripts/validate_repository_data_models.py`
- `docs/adr/0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md`
- `docs/workstreams/adr-0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/runbooks/remote-build-gateway.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/agent-session-workspace-isolation.md`
- `docs/adr/.index.yaml`
- `tests/test_remote_exec.py`
- `tests/test_repository_snapshot.py`
- `receipts/live-applies/2026-03-29-adr-0265-immutable-validation-snapshots-mainline-live-apply.json`
- `workstreams.yaml`

## Expected Live Surfaces

- controller-side `make remote-validate` and `make remote-pre-push` upload one
  immutable snapshot archive per run into the active `build-lv3` session
  workspace
- build-server validation executes from a fresh unpacked namespace under
  `.lv3-runs/` instead of a mutable mirrored checkout
- the build-server gate completes successfully from the latest realistic
  `origin/main` plus the ADR 0265 branch changes

## Verification Plan

- run focused tests for the snapshot builder, remote gateway, validation gate,
  and repo fallback logic
- run the broader local validation slices that cover the edited scripts and
  runbooks
- verify `make check-build-server`, `make remote-validate`, and `make
  remote-pre-push` from this isolated worktree against the live build server
- record one live-apply receipt with the snapshot id, remote run namespace, and
  end-to-end gate results after the latest-main replay passes

## Verification

- `LV3_SESSION_ID=adr-0265-main-race REMOTE_EXEC_VERBOSE=1 make check-build-server`
  passed from commit `768ab550`.
- `LV3_SESSION_ID=adr-0265-main-race REMOTE_EXEC_VERBOSE=1 make remote-validate`
  passed all six remote checks from the newest exact-main replay.
- Earlier in this session, the focused regression slice for
  `tests/test_repository_snapshot.py`, `tests/test_remote_exec.py`,
  `tests/test_validate_repo_cache.py`, `tests/test_validation_gate.py`,
  `tests/test_session_workspace.py`, and `tests/test_parallel_check.py`
  repeatedly passed while ADR 0265 was rebased forward across the concurrent
  mainline churn.

## Live Apply Outcome

- The newest exact-main replay from commit `768ab550` became the canonical ADR
  0265 mainline proof for repository version `0.177.78` and platform version
  `0.130.53`.

## Live Evidence

- `LV3_SESSION_ID=adr-0265-main-race REMOTE_EXEC_VERBOSE=1 make check-build-server`
  passed, built immutable snapshot
  `de22562164d38fb57a8f2dcfb8ab8c58a49094fbed15643b73df2ccf3b52fce0`, and
  verified dry-run upload under
  `/home/ops/builds/proxmox-host_server/.lv3-session-workspaces/adr-0265-main-race/repo/.lv3-runs/20260329T130452Z-de22562164d3/repo`.
- `LV3_SESSION_ID=adr-0265-main-race REMOTE_EXEC_VERBOSE=1 make remote-validate`
  passed all six remote checks from
  `/home/ops/builds/proxmox-host_server/.lv3-session-workspaces/adr-0265-main-race/repo/.lv3-runs/20260329T130506Z-de22562164d3/repo`.
- Canonical receipt:
  `receipts/live-applies/2026-03-29-adr-0265-immutable-validation-snapshots-mainline-live-apply.json`.

## Mainline Integration Outcome

- release `0.177.78` is the first repository version that records ADR 0265
  implemented on `main`
- platform version `0.130.53` is the first verified live platform version with
  immutable repository snapshots active on the remote build gateway
- shared integration files are updated in this branch already; the only
  remaining publish-time verification is the remote pre-push gate that runs
  automatically as part of `git push origin HEAD:main`
