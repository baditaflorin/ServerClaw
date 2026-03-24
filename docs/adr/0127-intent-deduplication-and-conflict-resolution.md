# ADR 0127: Intent Deduplication and Conflict Resolution

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The budgeted workflow scheduler (ADR 0119) uses a Postgres advisory lock to prevent concurrent instances of the same workflow. This solves the single-workflow concurrency problem but does not address a broader class of conflicts:

- Two different workflows that both modify the same service (e.g., `converge-netbox` and `rotate-netbox-db-password`) may run concurrently because they hold different advisory locks, even though the second one will fail if the first is mid-execution and has the service in a partially reconfigured state.
- The observation-to-action closure loop (ADR 0126) may generate an intent for the same service that an operator is already manually remediating in a separate CLI session.
- Two agents each processing a different alert for the same service may compile independent intents that together would leave the service in an inconsistent state.
- An agent may compile an intent that is semantically identical to a pending intent already in the ledger — a redundant execution that wastes budget.

The ledger (ADR 0115) records completed intents but does not prevent or coordinate future intents. The scheduler (ADR 0119) prevents concurrent executions of the same workflow but does not detect semantic conflicts between different workflows targeting the same resource.

The gap is a **conflict detection layer** that understands resource ownership and operation semantics, not just workflow identity. Without it, multi-agent operation is safe only if humans ensure agents do not target the same resources simultaneously — a fragile assumption that breaks under any incident scenario where multiple alerts fire at once.

## Decision

We will implement an **intent deduplication and conflict resolution** service as a pre-execution gate in the goal compiler (ADR 0112), evaluated after risk scoring (ADR 0116) and before submission to the budgeted scheduler (ADR 0119).

### Resource claim model

Every compiled `ExecutionIntent` declares a set of **resource claims**: the resources it will read or mutate. The goal compiler infers resource claims from the workflow's declared scope in the workflow catalog:

```json
// config/workflow-catalog.json
{
  "id": "converge-netbox",
  "resource_claims": [
    {"resource": "service:netbox",    "access": "write"},
    {"resource": "vm:netbox-vm",      "access": "read"},
    {"resource": "dns:netbox.lv3.org","access": "write"}
  ]
}
```

Resource claim access types: `read` (concurrent reads allowed), `write` (exclusive), `exclusive` (blocks all other claims on the resource including reads).

### Conflict detection

Before submitting an intent to the scheduler, the conflict detector queries the ledger for all intents in state `executing` or `pending_approval` (submitted but not yet approved):

```python
# platform/conflict/detector.py

def check(self, intent: ExecutionIntent) -> ConflictResult:
    active_claims = self._load_active_claims()  # From ledger: status IN ('executing', 'pending')

    for claim in intent.resource_claims:
        for active in active_claims:
            if self._conflicts(claim, active):
                return ConflictResult(
                    status="conflict",
                    conflicting_intent_id=active.intent_id,
                    conflicting_actor=active.actor_id,
                    conflict_type=self._conflict_type(claim, active),
                    resolution=self._suggest_resolution(claim, active),
                )

    return ConflictResult(status="clear")
```

### Conflict types and resolutions

| Conflict type | Example | Default resolution |
|---|---|---|
| `write_write` | Two converge workflows for the same service | Reject the later intent; suggest retry after first completes |
| `write_read` | Converge while a diagnostic read is in progress | Allow; diagnostic reads are non-blocking |
| `duplicate` | Same workflow, same target, same parameters within 5 minutes | Deduplicate: return the existing intent_id as the result |
| `cascade_conflict` | Modifying a service whose dependency is mid-deployment | Warn but allow; cascading behaviour is caller's responsibility |

### Deduplication window

If the incoming intent matches an existing intent by `(workflow_id, target_resource, canonical_params_hash)` and the existing intent completed within the last 5 minutes (configurable per workflow via `dedup_window_seconds` in the workflow catalog), the conflict detector returns the existing intent's output without re-executing. This prevents agents from re-running a workflow that already resolved the problem they were asked to fix.

```python
@dataclass
class ConflictResult:
    status:                 str       # 'clear' | 'conflict' | 'duplicate'
    conflicting_intent_id:  str | None
    conflicting_actor:      str | None
    conflict_type:          str | None
    resolution:             str | None  # 'reject' | 'deduplicate' | 'queue' | 'warn'
    dedup_result:           dict | None # If status='duplicate': the existing intent's output
```

### Resolution strategies

**Reject**: The later intent is rejected. The goal compiler returns `CONFLICT_REJECTED` with the conflicting intent's ID. The caller (agent or closure loop) should poll the ledger and retry once the blocking intent completes.

**Deduplicate**: The incoming intent is resolved as a no-op pointing at the existing intent's output. The ledger records a `intent.deduplicated` event linking both intent IDs. The caller receives the existing output as if it had executed.

**Queue**: Not implemented. Queuing is explicitly excluded (consistent with the scheduler's non-queuing design in ADR 0119). Callers must implement retry logic.

**Warn**: The intent proceeds but with a `conflict_warning` field in the compiled intent. Used for cascade conflicts where the platform cannot guarantee safe ordering but the operator/agent may have sufficient context to proceed.

### Claim registration and expiry

Active claims are stored in the ledger as `intent.claim_registered` events. Claims expire when the intent transitions to `executing.completed`, `executing.failed`, or `execution.budget_exceeded`. Claims also carry a TTL (equal to `max_duration_seconds` from the workflow budget plus a 60-second grace period) to prevent zombie claims from blocking indefinitely if the scheduler fails to write a completion event.

### Platform CLI integration

```bash
$ lv3 intent check "restart netbox"
Resource claims:
  service:netbox       write
  dns:netbox.lv3.org   write

Conflict check: CLEAR
No active intents targeting these resources.

$ lv3 intent check "rotate netbox db password"
Resource claims:
  service:netbox       write
  secret:netbox/db     write

Conflict check: CONFLICT
  converge-netbox [intent_id: abc-123] is executing (started 2 min ago, actor: agent/observation-loop)
  Resolution: reject — retry after converge-netbox completes (~3 min remaining)
```

## Consequences

**Positive**

- Write-write conflicts between concurrent agents targeting the same service are caught before execution, not discovered as a failed second deployment.
- Deduplication prevents duplicate work when two agents independently identify the same problem (e.g., two alerts for the same cert expiry both triggering triage).
- The conflict model is purely based on declared resource claims in the workflow catalog. It requires no runtime analysis of what each workflow actually does; the catalog is the ground truth.
- Conflict events in the ledger provide an audit trail of all rejected and deduplicated intents, making multi-agent coordination visible.

**Negative / Trade-offs**

- Resource claim declarations in the workflow catalog must be accurate. If a workflow touches a resource not declared in its claims, write-write conflicts for that resource will not be detected.
- The deduplication window (default 5 minutes) means that a legitimate second execution of the same workflow within 5 minutes of the first will be silently short-circuited. For idempotent workflows this is correct behaviour; for workflows with time-sensitive state (e.g., one-time token rotation) it could mask a real failure.
- TTL-based claim expiry is a heuristic. If the scheduler's watchdog kills a job mid-execution and fails to write a completion event, the claim will eventually expire, but the 60-second grace period means there is a window of false blocking.

## Boundaries

- Conflict detection applies only to intents that declare resource claims in the workflow catalog. Ad hoc Windmill workflows triggered outside the goal compiler are not subject to this gate.
- This ADR handles resource-level conflict detection. Lock contention between Windmill workers (scheduling, CPU, concurrency) remains the scheduler's (ADR 0119) responsibility.
- Conflict resolution is always reject-or-deduplicate. The platform does not attempt to merge or reorder conflicting intents.

## Related ADRs

- ADR 0044: Windmill (execution engine; workflows run after conflict gate passes)
- ADR 0048: Command catalog (resource_claims and dedup_window_seconds declared here)
- ADR 0090: Platform CLI (`lv3 intent check` command)
- ADR 0112: Deterministic goal compiler (conflict check is the final pre-submission gate)
- ADR 0115: Event-sourced mutation ledger (active claims loaded from here; conflict events written here)
- ADR 0116: Change risk scoring (risk scored before conflict check)
- ADR 0119: Budgeted workflow scheduler (receives intent only if conflict check passes)
- ADR 0124: Platform event taxonomy (platform.intent.rejected published on conflict)
- ADR 0125: Agent capability bounds (capability check precedes conflict check)
- ADR 0126: Observation-to-action closure loop (receives CONFLICT_REJECTED and handles retry)
