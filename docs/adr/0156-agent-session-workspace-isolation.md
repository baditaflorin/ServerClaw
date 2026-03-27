# ADR 0156: Agent Session Workspace Isolation

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.143.2
- Implemented In Platform Version: 0.130.9
- Implemented On: 2026-03-26
- Date: 2026-03-25

## Context

The repository already supports parallel ADR work through separate branches and git worktrees, but several runtime surfaces still shared mutable paths when two agent sessions ran at the same time:

- `scripts/remote_exec.sh` rsynced every build-server run into the same remote checkout under `config/build-server.json.workspace_root`, so one session could delete or overwrite another session's build or validation workspace.
- controller-side runtime state such as the scheduler watchdog store defaulted to a shared `.local` path unless the caller manually overrode it.
- generated status payloads and receipts carried no session namespace, which made it harder to distinguish concurrent runs in downstream audit surfaces.
- promotion-generated live-apply receipts used one base id per operation and had no built-in session suffix when the same promotion flow was exercised concurrently.

The platform needed one reusable session-workspace model that could be resolved from the current checkout or an explicit `LV3_SESSION_ID`, then threaded through every mutable surface that exists today.

## Decision

We implement a checkout-aware session workspace contract for controller automation.

Each session resolves a stable workspace identity with:

- `session_id`: explicit `LV3_SESSION_ID` when present, otherwise a stable checkout-derived identifier
- `session_slug`: normalized session identifier suitable for paths and NATS subjects
- `local_state_root`: `.local/session-workspaces/<session_slug>` under the current checkout
- `remote_workspace_root`: `<workspace_root>/.lv3-session-workspaces/<session_slug>/repo` on the build server
- `nats_prefix`: `platform.ws.<session_slug>`
- `state_namespace`: `ws:<session_slug>`
- `receipt_suffix`: `<session_slug>`

## Implementation Notes

### Session workspace resolver

`scripts/session_workspace.py` is the canonical resolver for session metadata. It:

- prefers `LV3_SESSION_ID` when the caller wants a human-chosen namespace
- falls back to a stable checkout-derived id so separate git worktrees do not collide
- emits either JSON or shell assignments so both Python tools and shell entrypoints can reuse the same contract

### Remote build-server isolation

`scripts/remote_exec.sh` now resolves a session workspace before contacting `docker-build-lv3`.

Instead of syncing into one shared checkout, it now uses:

```text
<workspace_root>/.lv3-session-workspaces/<session_slug>/repo
```

The remote gateway also:

- exports the session metadata into shell-mode and Docker-mode remote executions
- writes remote session-local state under the isolated checkout instead of a laptop-specific path
- prunes stale session directories older than two days as a best-effort cleanup step

### Controller-local state scoping

`platform.scheduler.watchdog.SchedulerStateStore` now uses `LV3_SESSION_LOCAL_ROOT` when present, so session-aware callers no longer share one `active-jobs.json` path.

`scripts/run_gate.py` records the resolved session workspace in the gate status payload so operators can trace which session produced a result.

### Audit and receipt scoping

`platform.ledger.writer.LedgerWriter` now attaches session workspace metadata to emitted records when the session environment is present.

`scripts.live_apply_receipts.receipt_id_with_session()` provides the canonical helper for appending a normalized session suffix to generated live-apply receipt ids. The ADR 0073 promotion pipeline now uses that helper for its production apply receipt id.

## Consequences

### Positive

- separate git worktrees now map to separate remote build-server checkouts by default
- session-aware controller tools can isolate local state without inventing their own path layout
- audit records and gate payloads now retain enough session context to understand which concurrent run produced them

### Trade-offs

- stale remote session directories are cleaned up opportunistically by the gateway rather than by a dedicated long-running janitor service
- the contract depends on callers exporting or preserving `LV3_SESSION_*` variables when they spawn nested tools outside the normal gateway flow

## Boundaries

- This ADR covers the mutable controller and build-server surfaces that exist in the current repository implementation.
- It does not yet introduce database-backed session registries or per-session Postgres schemas because those surfaces are not active runtime dependencies in the current repo-managed controller path.
- Canonical committed data still lives in the shared ledger, receipts, and repo history. Session scoping applies to ephemeral or intermediate execution state.

## Related ADRs

- ADR 0082: Remote build execution gateway
- ADR 0087: Repository validation gate
- ADR 0115: Event-sourced mutation ledger
- ADR 0119: Budgeted workflow scheduler
- ADR 0127: Intent deduplication and conflict resolution
