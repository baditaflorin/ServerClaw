# ADR 0127: Intent Deduplication and Conflict Resolution

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.122.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The budgeted workflow scheduler (ADR 0119) prevents concurrent instances of the same workflow, but it does not protect the broader multi-agent problem:

- different workflows can still target the same service concurrently
- the same corrective action can be submitted multiple times by different agents or operator sessions
- a workflow can begin while one of its direct dependencies is already mid-change

The platform needed a single pre-execution gate that understands declared resource ownership, rejects conflicting writes, short-circuits recently completed duplicates, and leaves a durable audit trail in the ledger.

## Decision

We implement an intent conflict gate in front of scheduler submission.

The implementation has four parts:

1. Every schedulable intent is compiled into resource claims, either from explicit `resource_claims` entries in `config/workflow-catalog.json` or from a conservative fallback derived from the target service, VM, and secret arguments.
2. An atomic conflict registry stores active claims in a shared state file under the git common directory, protected by an OS file lock so separate worktrees and concurrent local processes observe the same pending-intent view.
3. The scheduler registers claims before Windmill submission, rejects conflicting writes with `conflict_rejected`, records `intent.claim_registered` and `intent.deduplicated` ledger events, and releases claims on every terminal path.
4. The CLI exposes `lv3 intent check ...` so operators can inspect the inferred claims and current gate decision without submitting the workflow.

## Implementation Notes

### Claim model

Each claim is a `{resource, access}` pair where access is one of:

- `read`
- `write`
- `exclusive`

Conflicts are enforced as:

- `read` + `read`: allowed
- `read` + `write`: allowed
- `write` + `write`: rejected
- `exclusive` + anything: rejected

### Deduplication

Deduplication uses a signature of:

- `workflow_id`
- primary target resource
- canonical JSON argument hash

Mutation workflows default to a 300-second dedup window unless overridden by `dedup_window_seconds`. Diagnostic workflows default to `0` unless they opt in explicitly. A deduplicated submission returns the recorded output from the recent successful intent and emits `intent.deduplicated`.

### Cascade warnings

If a service is submitted while one of its direct dependencies from `config/dependency-graph.json` is already under an active write claim, the gate allows the intent but returns a `cascade_conflict` warning so the caller can surface the risk.

### Storage

The active registry is operational coordination state, not canonical business history. Ledger events remain the durable audit trail:

- `intent.claim_registered`
- `intent.deduplicated`
- `intent.rejected`
- existing execution lifecycle events from ADR 0115 and ADR 0119

## Consequences

### Positive

- conflicting service mutations are rejected before a second workflow starts
- duplicate fixes submitted moments apart collapse into one execution result
- racing worktrees on the same controller now coordinate through a shared registry instead of hidden local state
- operators can inspect the gate decision with `lv3 intent check`

### Trade-offs

- accuracy still depends on the workflow catalog describing real resource ownership
- the shared registry is controller-local coordination state; live distributed coordination still depends on the controller executing from the repo-managed path
- cascade warnings are advisory only and currently use direct dependency edges, not full transitive graph analysis

## Boundaries

- This ADR covers scheduler-facing intent gating only. It does not merge conflicting intents or introduce scheduler queueing.
- The registry uses TTL expiry to recover from abandoned submissions; it is not a replacement for watchdog termination or ledger completion events.
- Ad hoc mutations that bypass the scheduler do not participate in this gate.

## Related ADRs

- ADR 0090: Platform CLI
- ADR 0112: Deterministic goal compiler
- ADR 0115: Event-sourced mutation ledger
- ADR 0116: Change risk scoring
- ADR 0119: Budgeted workflow scheduler
- ADR 0123: Service uptime contracts and monitor-backed health
