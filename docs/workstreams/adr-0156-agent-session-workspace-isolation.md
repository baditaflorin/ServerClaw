# Workstream ADR 0156: Agent Session Workspace Isolation

- ADR: [ADR 0156](../adr/0156-agent-session-workspace-isolation.md)
- Title: per-session controller state, remote build workspace isolation, and session-aware receipt metadata
- Status: live_applied
- Branch: `codex/adr-0156-agent-session-workspace-isolation`
- Worktree: `.worktrees/adr-0156`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0087-validation-gate`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`, `adr-0127-intent-conflict-resolution`
- Conflicts With: none
- Shared Surfaces: `scripts/remote_exec.sh`, `scripts/session_workspace.py`, `scripts/run_gate.py`, `platform/scheduler/watchdog.py`, `platform/ledger/writer.py`, `scripts/live_apply_receipts.py`, `scripts/promotion_pipeline.py`, `docs/runbooks/`

## Scope

- add one reusable session-workspace resolver for both Python tools and shell entrypoints
- isolate the remote build gateway so concurrent sessions no longer share one checkout on `docker-build-lv3`
- scope scheduler runtime state to a session-local root when session metadata is present
- record session metadata in validation-gate payloads and ledger metadata
- add a canonical helper for session-suffixed live-apply receipt ids and wire the promotion pipeline onto it
- document the operator workflow for explicit session ids, remote layout, and troubleshooting

## Non-Goals

- introducing a new persistent controller database just for session tracking
- retrofitting every historical receipt with session metadata
- adding a long-running janitor workflow outside the existing build gateway path

## Expected Repo Surfaces

- `scripts/session_workspace.py`
- `scripts/remote_exec.sh`
- `scripts/run_gate.py`
- `platform/scheduler/watchdog.py`
- `platform/ledger/writer.py`
- `scripts/live_apply_receipts.py`
- `scripts/promotion_pipeline.py`
- `docs/adr/0156-agent-session-workspace-isolation.md`
- `docs/runbooks/agent-session-workspace-isolation.md`
- `docs/runbooks/remote-build-gateway.md`
- `docs/runbooks/validation-gate.md`
- `docs/workstreams/adr-0156-agent-session-workspace-isolation.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-build-lv3` receives remote syncs under a session-scoped subdirectory instead of one shared checkout
- explicit `LV3_SESSION_ID=<id>` runs preserve that namespace across remote shell, remote Docker, gate status payloads, and session-aware controller state
- stale remote session directories older than two days are pruned during normal gateway usage

## Verification

- `uv run --with pytest python -m pytest tests/test_session_workspace.py tests/test_remote_exec.py tests/test_validation_gate.py tests/test_live_apply_receipts.py tests/unit/test_ledger_writer.py tests/unit/test_scheduler_budgets.py -q`
- `uv run --with pytest python -m pytest tests/test_promotion_pipeline.py -q`
- `bash -n scripts/remote_exec.sh`
- `LV3_SESSION_ID=adr-0156-live make check-build-server`
- `LV3_SESSION_ID=adr-0156-live make remote-lint`

## Merge Criteria

- remote build-server syncs are isolated per session and keep worktree git metadata working
- session-aware controller state defaults no longer collide across concurrent runs
- validation and audit payloads preserve session metadata
- live verification from `main` proves the build-server route still works with the session-scoped layout

## Outcome

- the repository implementation first landed on `main` in repo release `0.143.2`, and the integrated live apply from current `main` is recorded in release `0.159.1`
- the 2026-03-26 live verification advanced platform version to `0.130.9` after `LV3_SESSION_ID=adr-0156-live make check-build-server` passed, the remote session workspace reported a valid git checkout path, and `LV3_SESSION_ID=adr-0156-live make remote-lint` completed successfully
- the live-apply branch also repaired stale build-server jump-host references, stopped forcing a full remote `.git-remote` wipe between session syncs, and cleared current ansible/yaml lint debt that was blocking the ADR 0156 gate on `main`
- the production ansible runner image on `docker-build-lv3` still carries an `ansible-lint` import mismatch, so the verified `remote-lint` run exercised the remote session workspace path and then completed through the command's built-in local fallback
