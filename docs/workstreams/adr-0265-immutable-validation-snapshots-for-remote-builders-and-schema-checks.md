# Workstream WS-0265: Immutable Validation Snapshots For Remote Builders And Schema Checks

- ADR: [ADR 0265](../adr/0265-immutable-validation-snapshots-for-remote-builders-and-schema-checks.md)
- Title: Replace mutable remote build mirrors with immutable validation snapshots
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0265-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0265-live-apply`
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

## Live Apply Outcome

- Pending live apply and exact-main verification.

## Live Evidence

- Pending live build-server replay.

## Mainline Integration Outcome

- Pending branch completion and merge-to-main release reconciliation.
