# ADR 0159: Speculative Parallel Execution with Compensating Transactions

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The resource lock registry (ADR 0153) and conflict detection (ADR 0127) use a **pessimistic concurrency** model: before executing, an agent acquires all required locks and checks for semantic conflicts. If a conflict is detected, the intent waits in the queue (ADR 0155) until locks are available.

Pessimistic concurrency is correct but over-conservative for a significant class of operations:

**Observation**: Two intents that lock different resources at the service level may still be independent in practice. But the conflict detector errs on the side of caution and may queue an intent that would have completed successfully if allowed to run in parallel.

Example: Two agents are running simultaneously:
- Agent A: `converge-netbox` — applying an Ansible config change to NetBox's Django settings.
- Agent B: `rotate-keycloak-client-secret` — calling the Keycloak API to rotate a client credential.

These two operations do not share any files, containers, or API endpoints. They would never conflict if run in parallel. But under pessimistic locking, if Agent A holds an `exclusive` lock on `vm:120/service:netbox` and Agent B needs to touch `vm:120/service:keycloak`, and both are in `lane:docker-runtime`, the lane's `max_concurrent_ops` budget might cause one to queue.

**Optimistic approach**: Allow both intents to run in parallel and detect a conflict only if it actually manifests at execution time. If it does, roll back the lower-priority intent using a compensating transaction.

This is only safe when:
1. Both operations are **reversible** (have a defined compensating transaction).
2. The conflict is **detectable** at execution time before it causes external observable harm.
3. The rollback cost is lower than the wait cost.

For the class of light-weight, idempotent, API-call-based operations (secret rotation, OIDC client config updates, DNS record updates, metric threshold changes), all three conditions are typically met.

## Decision

We will implement **speculative parallel execution** as an opt-in mode for operations that declare reversibility. Operations that are speculative-eligible run immediately in parallel, monitored for runtime conflicts. If a conflict manifests, the lower-priority operation is rolled back via its compensating transaction.

### Speculative eligibility criteria

A workflow is speculative-eligible if it declares all three in its workflow catalog entry:

```yaml
# config/workflow-catalog.yaml

- workflow_id: rotate-keycloak-client-secret
  speculative_eligible: true
  compensating_workflow_id: restore-keycloak-client-secret  # The undo operation
  conflict_detection_hook: check-keycloak-client-conflict   # Runtime conflict probe
  rollback_window_seconds: 300   # Max time after execution to detect and rollback

- workflow_id: update-dns-record
  speculative_eligible: true
  compensating_workflow_id: restore-dns-record
  conflict_detection_hook: check-dns-record-conflict
  rollback_window_seconds: 60

- workflow_id: rotate-openbao-token
  speculative_eligible: true
  compensating_workflow_id: restore-openbao-token
  conflict_detection_hook: check-openbao-token-conflict
  rollback_window_seconds: 120

# NOT speculative-eligible (no safe compensating transaction):
- workflow_id: converge-netbox
  speculative_eligible: false   # OS-level convergence is not easily reversible

- workflow_id: run-db-migration
  speculative_eligible: false   # Schema changes may be irreversible
```

### Speculative execution lifecycle

```
Standard (pessimistic):           Speculative:
  acquire lock                      submit immediately (no lock)
  wait if locked                    run in parallel with other specs
  execute                           runtime conflict probe at +30s
  release lock                      if conflict: run compensating tx
                                    if no conflict: commit to ledger
```

A speculative intent progresses through states:

```
SPECULATIVE_EXECUTING → SPECULATIVE_PROBING → SPECULATIVE_COMMITTED
                                            ↘ SPECULATIVE_ROLLED_BACK
```

### Runtime conflict detection

The `conflict_detection_hook` is a lightweight diagnostic workflow that runs 30 seconds after speculative execution completes. It checks whether another concurrent operation caused an inconsistency:

```python
# config/windmill/scripts/check-keycloak-client-conflict.py

def check_keycloak_client_conflict(intent: ExecutionIntent) -> ConflictReport:
    """
    Verify that the Keycloak client secret rotation completed cleanly
    and no other operation has since overwritten it.
    """
    # Read the actual current secret from Keycloak
    current_secret = keycloak.get_client_secret(intent.params["client_id"])

    # Compare with what our execution wrote to OpenBao
    our_secret = openbao.get(f"keycloak/clients/{intent.params['client_id']}/secret")

    if current_secret != our_secret:
        # Another operation wrote a different secret after us
        return ConflictReport(
            conflict_detected=True,
            conflict_type="post_execution_overwrite",
            other_intent_id=ledger.find_last_writer(f"keycloak/client/{intent.params['client_id']}"),
            priority_winner=determine_priority_winner(intent, other_intent)
        )

    return ConflictReport(conflict_detected=False)
```

### Compensating transaction execution

If a conflict is detected and the current intent is the lower-priority one:

```python
# platform/execution/speculative.py

def handle_conflict(intent: ExecutionIntent, conflict: ConflictReport):
    if conflict.priority_winner == intent.intent_id:
        # We win; the other operation's output is rolled back by their compensating tx
        ledger.write(
            event_type="execution.speculative_committed",
            intent_id=intent.intent_id,
            metadata={"conflict_resolved_in_our_favour": True}
        )
    else:
        # We lose; run our compensating transaction
        comp_workflow = load_workflow(intent.compensating_workflow_id)
        comp_intent = goal_compiler.compile_direct(
            workflow_id=comp_workflow.workflow_id,
            params=build_compensating_params(intent),
            actor_id="agent/speculative-rollback",
            parent_intent_id=intent.intent_id,
        )
        ledger.write(
            event_type="execution.speculative_rolled_back",
            intent_id=intent.intent_id,
            metadata={"compensating_intent_id": str(comp_intent.intent_id)}
        )
        # Re-queue the original intent to run after the winner completes
        intent_queue.enqueue(intent, priority=intent.priority, queue_after_intent=conflict.other_intent_id)
```

### Priority winner determination

When two speculative intents conflict, the winner is determined by:
1. Priority score (lower number = higher priority; ADR 0155 priority scale).
2. If equal priority: earlier `started_at` wins (first in, first kept).
3. If an incident-response intent conflicts with any other intent: incident response always wins.

### Agent awareness

When the goal compiler compiles an intent for a speculative-eligible workflow, it includes the speculative mode in the response:

```python
intent = goal_compiler.compile(
    instruction="rotate keycloak client secret for agent/triage-loop",
    allow_speculative=True,  # Opt-in; default is pessimistic
)
if intent.execution_mode == "speculative":
    print(f"Executing speculatively. Conflict check in 30s.")
    print(f"Compensating workflow: {intent.compensating_workflow_id}")
```

### Speculative execution monitoring

All speculative executions are tracked in a dedicated table:

```sql
CREATE TABLE platform.speculative_executions (
    intent_id           UUID PRIMARY KEY REFERENCES platform.execution_intents,
    probe_due_at        TIMESTAMPTZ NOT NULL,
    probe_workflow_id   TEXT NOT NULL,
    status              TEXT DEFAULT 'probing',  -- probing | committed | rolled_back
    conflict_with       UUID REFERENCES platform.execution_intents,
    compensating_intent UUID REFERENCES platform.execution_intents
);
```

The observation loop (ADR 0126) monitors `speculative_executions` for probe_due_at entries that have not been resolved in time (indicating the probe workflow failed or timed out). Unresolved probes trigger a CRITICAL finding.

## Consequences

**Positive**

- Operations that are empirically non-conflicting (the common case for lightweight API operations) complete in parallel without queuing, significantly reducing overall latency for multi-agent workloads.
- The compensating transaction model makes rollback first-class: it is defined at workflow-authoring time, tested alongside the forward workflow, and invoked automatically on conflict detection.

**Negative / Trade-offs**

- Speculative execution is only safe for reversible operations. Determining reversibility correctly is the hardest part; an incorrect `compensating_workflow_id` (that doesn't actually undo the forward operation) creates inconsistency that is worse than the original conflict.
- There is a window between speculative execution and the conflict probe during which the platform is in a potentially inconsistent state (two concurrent writes have happened, neither confirmed). External systems that query platform state in this window may observe inconsistency. This is acceptable for most operations but rules out speculative mode for changes with immediate external visibility (e.g., DNS record changes that propagate before the probe window).
- Rollback of a rolled-back intent followed by re-queuing adds to queue depth. If many speculative intents conflict simultaneously, the queue fills rapidly.

## Boundaries

- Speculative execution is opt-in at the workflow level. The default mode is pessimistic (lock before execute). No workflow is forced into speculative mode.
- Speculative mode is not applicable to Ansible convergence, Docker Compose operations, database migrations, or any operation with filesystem side effects. These are inherently non-reversible at the platform level.

## Related ADRs

- ADR 0044: Windmill (compensating workflows are Windmill jobs)
- ADR 0112: Deterministic goal compiler (speculative mode flag)
- ADR 0115: Event-sourced mutation ledger (speculative_committed / speculative_rolled_back events)
- ADR 0124: Platform event taxonomy (new speculative execution event types)
- ADR 0153: Distributed resource lock registry (speculative intents skip lock acquisition)
- ADR 0155: Intent queue (rolled-back intents re-queued here)
- ADR 0126: Observation-to-action closure loop (unresolved probe findings)
- ADR 0162: Distributed deadlock detection (compensating transactions don't create new locks; deadlock-safe by design)
