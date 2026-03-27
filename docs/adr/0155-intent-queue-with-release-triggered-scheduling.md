# ADR 0155: Intent Queue with Release-Triggered Scheduling

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.158.0
- Implemented In Platform Version: 0.130.7
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

When the goal compiler (ADR 0112) or conflict detector (ADR 0127) rejects an intent due to a resource conflict, the current behaviour is: the caller receives a `ConflictRejected` error and is responsible for retrying. There is no platform-level mechanism to buffer the intent and attempt it again when the blocking resource is released.

In practice, this means:
- **Agents must implement their own retry logic.** Each agent that encounters a conflict decides independently when to retry (typically with a fixed sleep or exponential backoff). This is inefficient and does not coordinate across agents.
- **Agents poll instead of waiting.** An agent blocked on a resource must either sleep-poll the conflict detector or subscribe to ledger events and manually determine when the blocking intent has completed.
- **Intents can be dropped.** If an agent's session context expires (24-hour TTL on ADR 0130 state) before a conflict clears, the intent is never retried.
- **Priority is not respected.** If three agents are waiting for the same lane, there is no guarantee that the highest-priority intent executes first when the lane opens.

This creates a gap in the parallelism model: even if the lock registry (ADR 0153) and execution lanes (ADR 0154) enable concurrent work across different resources, work targeting the same resource degrades to uncoordinated retry storms.

The correct architecture is a **durable intent queue** with **release-triggered scheduling**: intents that cannot execute immediately are buffered in a Postgres-backed queue, and when a resource is released (lock release event, intent completion event), the queue scheduler wakes up and submits the next eligible intent.

## Decision

We will implement a **durable intent queue** with priority scheduling and release-triggered dispatch as a platform service.

The first repository implementation lands in [`platform/intent_queue/scheduler_store.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/intent_queue/scheduler_store.py), [`platform/scheduler/scheduler.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py), [`scripts/intent_queue_dispatcher.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/intent_queue_dispatcher.py), and the Windmill runtime defaults. It keeps the existing ADR 0162 queue state intact while adding a scheduler-owned queue for workflow-busy and conflict-rejected intents, release-triggered dispatcher spawning, a repo-managed Windmill safety schedule, and CLI/operator surfaces.

### Queue table schema

```sql
-- In the platform Postgres instance, migration: 0155_intent_queue.sql
CREATE TABLE platform.intent_queue (
    queue_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_id       UUID NOT NULL REFERENCES platform.execution_intents(intent_id),
    actor_id        TEXT NOT NULL,
    context_id      UUID NOT NULL,
    required_lanes  TEXT[] NOT NULL,    -- e.g., ['lane:docker-runtime']
    required_locks  JSONB NOT NULL,     -- Resource lock specs from ADR 0153
    priority        INTEGER NOT NULL DEFAULT 50,  -- 0 = highest, 100 = lowest
    queued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,          -- Max wait time; after this → notify agent
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_conflict   TEXT,              -- Reason for most recent conflict
    status          TEXT NOT NULL DEFAULT 'waiting',  -- waiting | dispatching | expired | dispatched
    notify_channel  TEXT,              -- NATS subject to notify when dispatched
    CONSTRAINT priority_range CHECK (priority BETWEEN 0 AND 100)
);

CREATE INDEX intent_queue_lanes_gin ON platform.intent_queue USING GIN (required_lanes);
CREATE INDEX intent_queue_status_priority ON platform.intent_queue (status, priority, queued_at)
    WHERE status = 'waiting';
```

### Priority assignment

Priority is determined at queue-time by the goal compiler based on the intent's context:

| Intent source | Priority | Rationale |
|---|---|---|
| Incident response runbook (ADR 0129) | 5 | Highest; system is degraded |
| Observation loop critical finding | 10 | Platform health risk |
| Operator-triggered via CLI (`lv3 run`) | 20 | Operator is waiting |
| Triage engine auto-remediation | 40 | Automated, non-urgent |
| Observation loop drift remediation | 60 | Scheduled maintenance |
| Background index rebuild | 80 | Housekeeping |
| Scheduled (non-health-related) | 90 | Best-effort |

### Release-triggered dispatch

The queue scheduler subscribes to two NATS topics that indicate a resource has become available:
- `platform.locks.released.{resource}` — A lock was released (ADR 0153).
- `platform.execution.completed` and `platform.execution.failed` — An intent finished (ADR 0124).

On receiving either event, the scheduler runs a **targeted dispatch scan** for intents in the queue that require the just-released resource:

```python
# config/windmill/scripts/intent-queue-dispatcher.py

@nats.subscribe("platform.locks.released.>")
def on_lock_released(subject: str, payload: dict):
    released_resource = subject.replace("platform.locks.released.", "")
    dispatch_eligible(resource_hint=released_resource)

@nats.subscribe("platform.execution.completed")
@nats.subscribe("platform.execution.failed")
def on_execution_done(payload: dict):
    for lane in payload.get("lanes_held", []):
        dispatch_eligible(lane_hint=lane)

def dispatch_eligible(resource_hint: str = None, lane_hint: str = None):
    # Find highest-priority waiting intent whose required resources are now available
    candidates = db.query("""
        SELECT * FROM platform.intent_queue
        WHERE status = 'waiting'
          AND expires_at > now()
          AND (
              :resource_hint = ANY(required_locks->'resources')
              OR :lane_hint = ANY(required_lanes)
          )
        ORDER BY priority ASC, queued_at ASC
        LIMIT 10
        FOR UPDATE SKIP LOCKED
    """, resource_hint=resource_hint, lane_hint=lane_hint)

    for intent in candidates:
        if try_acquire_locks(intent):
            submit_to_windmill(intent)
            db.execute("UPDATE platform.intent_queue SET status='dispatched' WHERE queue_id=:id", id=intent.queue_id)
            nats.publish(intent.notify_channel, {"status": "dispatched", "intent_id": intent.intent_id})
```

`FOR UPDATE SKIP LOCKED` ensures that two concurrent dispatcher invocations do not double-dispatch the same queue entry.

### Intent expiry

When `expires_at` is reached and the intent has not been dispatched:
1. The intent's status is set to `expired`.
2. The agent that submitted it is notified on its `notify_channel`.
3. The notification includes `last_conflict` (why it was blocked) and a recommendation:
   - If the blocking resource is in a degraded VM: escalate via handoff protocol (ADR 0131).
   - If the blocking resource has been held for > TTL: suspected deadlock; trigger deadlock detector (ADR 0162).

### Agent API for queuing

The goal compiler's `compile()` method is extended with a `queue_if_conflicted` flag:

```python
# platform CLI and agent code
intent = goal_compiler.compile(
    instruction="rotate keycloak client secret for agent/triage-loop",
    actor_id="agent/claude-code",
    queue_if_conflicted=True,
    queue_expires_in=timedelta(minutes=30),
    queue_priority=20,
    notify_on_dispatch="platform.agent.intent_dispatched.ctx:abc123",
)

if intent.status == "queued":
    # Agent receives a queue handle, not a blocking wait
    print(f"Intent queued at position {intent.queue_position}. Will notify when ready.")
    # Agent can now proceed with other work while waiting
```

This is **non-blocking**: the agent submits the intent, receives confirmation that it's queued, and continues. When the intent is dispatched, the agent receives a NATS notification and can resume tracking the execution.

### Queue health monitoring

The queue depth is a platform health signal. A queue with many high-priority intents waiting indicates systemic contention. The observation loop (ADR 0126) monitors:
- `platform.queue.depth` — total intents waiting.
- `platform.queue.high_priority_depth` — intents with priority ≤ 20 waiting.
- `platform.queue.oldest_wait_seconds` — age of the oldest waiting intent.

If `high_priority_depth > 5` or `oldest_wait_seconds > 600`, a `platform.findings.queue_congestion` finding is emitted.

## Consequences

**Positive**

- Agents no longer implement ad hoc retry logic. The platform owns the retry/dispatch cycle, ensuring consistent priority ordering and no intent drops.
- Agents working on different goals can proceed concurrently: if one intent is queued waiting for a resource, the agent immediately continues with other intents rather than blocking.
- Priority ordering ensures that incident response always jumps the queue ahead of background housekeeping — even if the housekeeping intent was submitted first.

**Negative / Trade-offs**

- The queue is a new durable Postgres table that must be backed up, monitored, and maintained. A large backlog in the queue (many queued intents) may indicate that the platform is being asked to do more than it can handle and needs operator review.
- Non-blocking dispatch means an agent may proceed with intent B while intent A is queued. If A and B have an implicit ordering dependency that the conflict detector does not model, the agent must explicitly check for this before submitting B with `queue_if_conflicted=True`.

## Boundaries

- The intent queue buffers intents that cannot execute due to resource conflicts. It does not buffer intents that are rejected for semantic reasons (e.g., violating agent capability bounds, failing the health composite index gate). Those are hard rejections that require escalation.
- The queue is not a task scheduler for recurring jobs. Scheduled tasks use Windmill's native scheduling. The queue is specifically for conflict-delayed intents.

## Related ADRs

- ADR 0044: Windmill (execution target; submit_to_windmill in dispatcher)
- ADR 0058: NATS event bus (release events trigger dispatch; notify_channel for agents)
- ADR 0112: Deterministic goal compiler (submits to queue on conflict; queue_if_conflicted flag)
- ADR 0115: Event-sourced mutation ledger (platform.execution.* events trigger dispatch)
- ADR 0124: Platform event taxonomy (platform.queue.* events for monitoring)
- ADR 0126: Observation-to-action closure loop (queue congestion finding feeds closure loop)
- ADR 0127: Intent conflict detection (semantic conflicts are hard rejections; resource conflicts go to queue)
- ADR 0153: Distributed resource lock registry (locks acquired at dispatch time)
- ADR 0154: VM-scoped execution lanes (lane capacity checked at dispatch time)
- ADR 0162: Distributed deadlock detection (triggered by expired queue entries)
