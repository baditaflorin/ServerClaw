# ADR 0165: Workflow Idempotency Keys and Double-Execution Prevention

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.153.0
- Implemented In Platform Version: 0.130.6
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The workflow scheduler already enforces workflow budgets (ADR 0119) and rejects overlapping writes through the conflict registry (ADR 0127), but neither of those mechanisms answers the retry-safety problem:

- a network timeout during Windmill submission can leave the caller unsure whether the job was accepted
- an agent restart can re-submit the same workflow without a durable submission handle
- a NATS-triggered closure-loop run can be delivered more than once and compile the same remediation twice

Without a durable idempotency contract, retrying a legitimate failure can cause a second live mutation. That is unacceptable for rotation, rollback, and remediation workflows.

## Decision

We will add a repository-managed idempotency layer on the workflow submission path.

The first implementation in `0.153.0` adds four concrete surfaces:

1. `platform.idempotency.keys.compute_idempotency_key()` for deterministic workflow submission keys.
2. `platform.idempotency.IdempotencyStore` with a shared git-common-dir file fallback and a Postgres-backed `platform.idempotency_records` table for live runtimes.
3. Scheduler integration in [`platform/scheduler/scheduler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py), which checks the idempotency store before conflict handling or Windmill submission, returns cached results for completed hits, and returns `in_flight` for duplicate active submissions.
4. Operator visibility through `lv3 intent status <intent_id>` plus the new ledger event type `execution.idempotent_hit`.

## Implementation

### Key construction

The idempotency key is derived from:

- workflow ID
- resolved workflow target service or VM
- normalized workflow arguments with volatile fields stripped
- requesting actor ID
- either a time bucket or an explicit event scope

The implementation normalizes argument ordering, drops timestamp-style fields, and replaces UUID or ISO timestamp scalar values with stable sentinels before hashing. This keeps retries stable while still allowing a later operational window to generate a fresh key.

### Store behavior

The store keeps one record per key with `in_flight`, `completed`, `failed`, `aborted`, `budget_exceeded`, or `rolled_back` status.

- `completed` returns the cached result immediately and emits `execution.idempotent_hit`.
- `in_flight` returns the original job handle instead of re-submitting.
- non-completed terminal states are treated as retryable and are replaced by a fresh record on the next submission.

For local development and parallel worktrees, the default store lives in the git common directory so the protection applies across worktrees, not just inside one checkout.

For live runtime deployments, the canonical schema is [`migrations/0016_idempotency_store.sql`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0016_idempotency_store.sql).

### Scheduler and closure-loop integration

The budgeted scheduler now:

- computes an idempotency key before conflict registration
- returns `idempotent_hit` for completed duplicates
- returns `in_flight` for active duplicates
- stores the Windmill job ID after submission
- finalizes the record on success, failure, abort, or budget exhaustion

The closure loop now passes its `trigger_ref` into the scheduler as an explicit idempotency scope so re-delivery of the same closure-loop trigger does not create a second execution.

### Operator visibility

`lv3 intent status <intent_id>` now reads ledger/idempotency state and reports when an intent was served by an idempotency hit, including the original job reference and cached result payload.

## Consequences

### Positive

- scheduler retries are safe after ambiguous submission failures
- duplicate closure-loop triggers do not create duplicate live workflows
- operators can distinguish a cached replay from a fresh execution

### Negative / Trade-offs

- the live path now depends on the Windmill converge applying `migrations/0016_idempotency_store.sql` before scheduler runtimes rely on the Postgres-backed store
- an ambiguous submission failure can leave an `in_flight` record without a job ID until the TTL expires
- manual shell-triggered operations that bypass the scheduler still do not benefit from this protection

## Related ADRs

- ADR 0044: Windmill
- ADR 0058: NATS JetStream for internal event delivery
- ADR 0112: Deterministic goal compiler
- ADR 0115: Event-sourced mutation ledger
- ADR 0119: Budgeted workflow scheduler
- ADR 0126: Observation-to-action closure loop
- ADR 0127: Intent deduplication and conflict resolution
- ADR 0130: Agent state persistence across workflow boundaries
