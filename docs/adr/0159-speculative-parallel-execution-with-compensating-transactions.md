# ADR 0159: Speculative Parallel Execution with Compensating Transactions

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.144.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

ADR 0119 and ADR 0127 give the platform a safe pessimistic scheduler:

- per-workflow concurrency limits stop duplicate workflow fan-out
- resource claims reject overlapping writes before a second workflow starts
- duplicate suppression reuses recent outputs when the same intent is submitted twice

That model is correct, but conservative. Some workflows are reversible and can safely start even when another workflow already holds a conflicting write claim. Secret rotation and similar API-scoped changes are the main example: waiting for the first writer to finish is safe, but not always necessary if the later writer can detect a conflict and compensate cleanly.

The platform needed a way to:

1. let explicitly reversible workflows bypass the pessimistic conflict rejection path
2. keep the audit trail explicit in the mutation ledger
3. run a post-execution probe before treating the speculative result as committed
4. launch a compensating workflow automatically when the speculative execution loses

## Decision

The repository now implements speculative execution as an opt-in extension of the existing scheduler and conflict registry.

The first implementation in `0.144.0` adds:

- a `speculative` policy block in `config/workflow-catalog.json`
- goal-compiler support for `allow_speculative=True` and CLI support for `lv3 run --allow-speculative`
- scheduler support for speculative conflict registration, probe execution, commit, and compensating rollback
- persisted speculative execution state under `.local/scheduler/speculative-executions.json`
- ledger event types for `execution.speculative_started`, `execution.speculative_probing`, `execution.speculative_committed`, and `execution.speculative_rolled_back`

## Implementation

### Catalog schema

Workflows opt in with a `speculative` block:

```json
{
  "speculative": {
    "eligible": true,
    "compensating_workflow_id": "restore-netbox-db-password",
    "conflict_probe": {
      "path": "platform/scheduler/speculative_hooks.py",
      "callable": "probe_netbox_secret_rotation"
    },
    "probe_delay_seconds": 30,
    "rollback_window_seconds": 300
  }
}
```

The repository validator rejects incomplete speculative metadata. A speculative workflow must declare:

- `eligible: true`
- a valid `compensating_workflow_id`
- a probe callable loaded by `path` or `module`
- integer `probe_delay_seconds` and `rollback_window_seconds`

### Goal compiler and CLI

The goal compiler keeps pessimistic mode as the default. When the caller explicitly opts in and the workflow catalog marks the workflow speculative-eligible, the compiled intent changes to:

- `execution_mode: speculative`
- `compensating_workflow_id: ...`
- `rollback_window_seconds: ...`

The CLI exposes this through:

```bash
lv3 run --allow-speculative "deploy netbox"
```

Direct workflow IDs use the same path when `--allow-speculative` is present so the intent and scheduler metadata stay aligned.

### Scheduler path

The scheduler still enforces actor policy, host-touch budgets, rollback-depth limits, and deduplication. The speculative differences are:

1. workflow-level concurrency locks are skipped
2. conflicting resource claims are registered with `allow_conflicts=True` instead of being rejected
3. the forward workflow runs normally
4. after a successful terminal state, the scheduler records `execution.speculative_probing` and runs the configured probe
5. if the probe reports no conflict, the execution is committed
6. if the probe reports that another intent won, the scheduler launches the compensating workflow automatically and records `execution.speculative_rolled_back`

The claim remains active through the probe and rollback window so other submissions still see the in-flight speculative mutation until it is committed or rolled back.

### Probe loading and rollback arguments

The repository implementation loads probe callables from either:

- `speculative.conflict_probe.path`
- `speculative.conflict_probe.module`

The callable receives a dictionary context containing:

- `workflow_id`
- `actor_intent_id`
- `job_id`
- original `arguments`
- `requested_by`
- inferred `resource_claims`
- the initially conflicting intent id, when one existed

Compensating workflows receive the original arguments plus scheduler-added rollback metadata such as:

- `parent_actor_intent_id`
- `rollback_parent_intent_id`
- `speculative_rollback_of`
- `speculative_original_workflow_id`
- `speculative_conflict`

## Consequences

### Positive

- reversible workflows can bypass pessimistic write rejection without bypassing the rest of the scheduler contract
- speculative executions now have first-class ledger events and persisted probe state
- rollback is automatic and auditable instead of being an operator-only follow-up

### Trade-offs

- the framework is implemented, but current `main` intentionally does not mark production workflows speculative-eligible until each one has a reviewed probe and a trustworthy compensating path
- probe quality is the safety boundary; a weak probe turns speculative mode into guesswork
- speculative rollback currently runs as an internal scheduler action, not as a human-approved top-level intent

## Boundaries

- speculative mode is opt-in and mutation-only
- diagnostic workflows remain unchanged
- the first repository implementation is controller-side only; no platform version bump is claimed until a speculative-enabled workflow is applied and validated from `main`

## Related ADRs

- ADR 0115: Event-sourced mutation ledger
- ADR 0119: Budgeted workflow scheduler
- ADR 0124: Platform event taxonomy and canonical NATS topics
- ADR 0127: Intent deduplication and conflict resolution
