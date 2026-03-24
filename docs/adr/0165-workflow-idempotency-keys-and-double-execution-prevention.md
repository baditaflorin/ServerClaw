# ADR 0165: Workflow Idempotency Keys and Double-Execution Prevention

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform's workflow execution model has a fundamental correctness gap: it is possible to submit the same workflow twice and have it execute twice. This happens in three real scenarios:

**Scenario 1: Network failure during submission.** An agent submits a workflow to Windmill and the request times out before the response arrives. The agent does not know whether Windmill received the request. With the retry policy (ADR 0163), the agent retries. If Windmill did receive the original request, both the original and the retry execute. Two concurrent `rotate-keycloak-client-secret` runs produce two different new secrets, the second overwriting the first, leaving OpenBao and Keycloak out of sync.

**Scenario 2: Agent crash and recovery.** An agent submits a workflow and then crashes (Windmill job killed, container restart). On recovery, the agent's state (ADR 0130) may indicate the workflow was "in progress" but the new session does not know the Windmill job ID. The recovery logic resubmits the intent, running the workflow a second time while the original is still executing.

**Scenario 3: Duplicate NATS delivery.** The closure loop (ADR 0126) is triggered by a NATS event `platform.health.degraded`. NATS JetStream guarantees at-least-once delivery. Under network partition, the same event may be delivered twice, causing two instances of the remediation workflow to be submitted.

Current mitigations:
- `max_concurrent_instances` in the workflow budget (ADR 0119) prevents concurrent duplicate runs for workflows with `max_concurrent_instances: 1`. But this is advisory (Postgres advisory lock), does not distinguish "retry of the same job" from "second distinct invocation", and does not apply to workflows with `max_concurrent_instances > 1`.
- The conflict detector (ADR 0127) detects duplicate intents via `event_type: duplicate` — "same workflow, same target, same params within 5 minutes." This is a heuristic, not a guarantee.

Neither mechanism provides the transactional guarantee: *if a workflow was successfully submitted and completed, a second submission with the same intent returns the first result rather than running again.*

## Decision

We will implement **idempotency keys** for all workflow submissions. A submission with an idempotency key that has already succeeded returns the cached result immediately without re-executing the workflow.

### Idempotency key construction

An idempotency key is a deterministic hash of the intent's identifying parameters:

```python
# platform/idempotency/keys.py

def compute_idempotency_key(
    workflow_id: str,
    target_service_id: str,
    params: dict,
    actor_id: str,
    time_window_minutes: int = 60,
) -> str:
    """
    Compute a time-windowed idempotency key.

    The time window prevents the same parameters from being deduplicated
    across different operational windows (e.g., a daily rotation should
    not be deduplicated against yesterday's rotation).
    """
    # Normalise params: sort keys, strip volatile fields (timestamps, UUIDs in values)
    stable_params = normalise_params(params)
    window = now().replace(second=0, microsecond=0)
    window = window - timedelta(minutes=window.minute % time_window_minutes)

    key_material = {
        "workflow_id": workflow_id,
        "target_service_id": target_service_id,
        "params_hash": sha256(json.dumps(stable_params, sort_keys=True)).hexdigest(),
        "actor_id": actor_id,
        "window": window.isoformat(),
    }
    return "idem:" + sha256(json.dumps(key_material, sort_keys=True)).hexdigest()[:32]
```

### Idempotency store

```sql
-- platform/migrations/0165_idempotency_store.sql
CREATE TABLE platform.idempotency_records (
    idempotency_key TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    actor_id        TEXT NOT NULL,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'in_flight',
                    -- 'in_flight' | 'completed' | 'failed'
    result          JSONB,          -- Cached result (for completed)
    windmill_job_id TEXT,           -- The actual Windmill job ID
    intent_id       UUID,
    expires_at      TIMESTAMPTZ NOT NULL  -- Auto-expire records after TTL
);

-- Partial index: fast lookup for in-flight records
CREATE INDEX idempotency_in_flight ON platform.idempotency_records (idempotency_key)
    WHERE status = 'in_flight';
```

### Goal compiler integration

The goal compiler (ADR 0112) checks the idempotency store before submitting to Windmill:

```python
# platform/compiler/goal_compiler.py

def compile_and_execute(self, intent: ExecutionIntent) -> ExecutionResult:
    idem_key = compute_idempotency_key(
        workflow_id=intent.workflow_id,
        target_service_id=intent.target_service_id,
        params=intent.params,
        actor_id=intent.actor_id,
    )

    # CHECK: does a record exist for this key?
    existing = db.query(
        "SELECT * FROM platform.idempotency_records WHERE idempotency_key = :key FOR UPDATE",
        key=idem_key,
    )

    if existing:
        if existing.status == "completed":
            # Return cached result — do not re-execute
            ledger.write(
                event_type="execution.idempotent_hit",
                intent_id=intent.intent_id,
                metadata={"original_job_id": existing.windmill_job_id},
            )
            return ExecutionResult(
                status="idempotent_hit",
                result=existing.result,
                windmill_job_id=existing.windmill_job_id,
            )
        elif existing.status == "in_flight":
            # Another execution is in progress; return a handle to monitor it
            return ExecutionResult(
                status="in_flight",
                windmill_job_id=existing.windmill_job_id,
                message="Execution already in progress with the same idempotency key.",
            )
        elif existing.status == "failed":
            # Previous attempt failed; allow retry by deleting the failed record
            db.execute(
                "DELETE FROM platform.idempotency_records WHERE idempotency_key = :key",
                key=idem_key,
            )
            # Fall through to fresh submission

    # INSERT record (under transaction lock from FOR UPDATE above)
    db.execute("""
        INSERT INTO platform.idempotency_records
            (idempotency_key, workflow_id, actor_id, status, intent_id, expires_at)
        VALUES (:key, :wf, :actor, 'in_flight', :intent_id, now() + interval '2 hours')
    """, key=idem_key, wf=intent.workflow_id, actor=intent.actor_id, intent_id=intent.intent_id)

    # Submit to Windmill
    job_id = windmill.submit_job(intent)
    db.execute(
        "UPDATE platform.idempotency_records SET windmill_job_id=:job_id WHERE idempotency_key=:key",
        job_id=job_id, key=idem_key,
    )
    return ExecutionResult(status="submitted", windmill_job_id=job_id)
```

On completion (success or failure), the workflow finaliser updates the record:

```python
# In the Windmill job finaliser (called at end of every job)
def finalise_idempotency_record(idem_key: str, status: str, result: dict):
    db.execute("""
        UPDATE platform.idempotency_records
        SET status=:status, result=:result, completed_at=now()
        WHERE idempotency_key=:key
    """, status=status, result=json.dumps(result), key=idem_key)
```

### Idempotency for NATS-triggered workflows

For workflows triggered by NATS events (e.g., the closure loop responding to `platform.health.degraded`), the NATS message ID is used as part of the idempotency key:

```python
# In the closure loop NATS subscriber
def on_health_degraded(msg: nats.Msg):
    idem_key = compute_idempotency_key(
        workflow_id="auto-remediate",
        target_service_id=msg.data["service_id"],
        params={"signal": msg.data["signal"]},
        actor_id="agent/closure-loop",
        # Use the NATS message sequence as the time window anchor
        # so the same message, re-delivered, produces the same key
        time_window_minutes=0,  # Exact window (no bucketing); keyed on message ID
        nats_message_id=msg.metadata.sequence,
    )
```

This ensures that NATS at-least-once delivery of the same event does not cause duplicate remediations.

### Expiry and cleanup

Records expire after 2 hours by default. A nightly Windmill workflow `cleanup-idempotency-records` deletes records past `expires_at`:

```sql
DELETE FROM platform.idempotency_records WHERE expires_at < now();
```

### Operator visibility

The `lv3 intent status <intent_id>` CLI command shows if an intent was an idempotency hit:

```
$ lv3 intent status abc123
Intent abc123: rotate-keycloak-client-secret (agent/claude-code)
Status: idempotent_hit
Original execution: xyz789 (completed 4m ago)
Result: {"new_secret_id": "sec_001", "rotated_at": "2026-03-24T14:28:00Z"}
No action taken. The original result is being returned.
```

## Consequences

**Positive**

- Network failures during workflow submission are safe to retry. The retry either returns the cached result (if the original completed) or joins the in-flight execution (if it is still running) — never causes a duplicate execution.
- NATS at-least-once delivery is safe for workflow triggering. Duplicate NATS messages produce idempotency hits, not duplicate executions.
- Secret rotation workflows (`rotate-keycloak-client-secret`, `rotate-openbao-token`) become safe to invoke concurrently from multiple agents. Only one execution runs; others receive the cached result.

**Negative / Trade-offs**

- Idempotency records stored in Postgres add write overhead to every workflow submission. For a platform running 50 workflows per day this is negligible; for platforms running hundreds of workflows per minute it would require a cache layer (Redis).
- The `failed` record deletion (allowing retry of failed workflows) means that a workflow that always fails will be retried indefinitely. The retry policy (ADR 0163) provides the outer limit on retry attempts; idempotency deduplication operates within a single retry attempt.
- The 2-hour expiry window means that the same workflow run with the same parameters more than 2 hours apart is not deduplicated. For daily scheduled rotations, the 60-minute time window ensures each day's rotation runs independently.

## Boundaries

- Idempotency keys prevent double-execution of submitted workflows. They do not prevent duplicate intent compilation (the goal compiler can compile the same instruction twice into two separate intents with different intent IDs). The conflict detector (ADR 0127) handles semantic deduplication at the intent level.
- This ADR governs platform-managed workflows. Manual Ansible playbook runs via Semaphore (ADR 0149) or the operator's terminal are not subject to idempotency key checks.

## Related ADRs

- ADR 0044: Windmill (job submission target; finaliser updates idempotency record)
- ADR 0058: NATS event bus (at-least-once delivery; NATS message ID used in key construction)
- ADR 0112: Deterministic goal compiler (idempotency check before Windmill submission)
- ADR 0115: Event-sourced mutation ledger (execution.idempotent_hit events)
- ADR 0126: Observation-to-action closure loop (NATS-triggered workflow deduplication)
- ADR 0127: Intent conflict detection (semantic deduplication; complementary to idempotency)
- ADR 0163: Retry taxonomy (retry of a submission with the same key is safe due to idempotency)
