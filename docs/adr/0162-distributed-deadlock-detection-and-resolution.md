# ADR 0162: Distributed Deadlock Detection and Resolution

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.150.0
- Implemented In Platform Version: 0.130.11
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

With resource locks (ADR 0153), execution lanes (ADR 0154), intent queuing (ADR 0155), and concurrent agent sessions, the platform now has the full set of conditions under which **distributed deadlocks** can arise:

**Classic deadlock scenario:**
- Agent A holds a lock on `vm:120/service:netbox` and is waiting to acquire `vm:120/service:keycloak`.
- Agent B holds a lock on `vm:120/service:keycloak` and is waiting to acquire `vm:120/service:netbox`.
- Neither agent can proceed. Both wait indefinitely.

**Lane-level deadlock scenario:**
- Agent A is executing in `lane:docker-runtime` and attempting to acquire `lane:postgres` (because it needs a schema migration).
- Agent B is executing in `lane:postgres` and attempting to acquire `lane:docker-runtime` (because it needs to update a service that reads from Postgres).
- Both lanes are "full" from the other agent's perspective.

**Queue + lock deadlock scenario:**
- Intent X is queued waiting for lock L1 to be released by Intent Y.
- Intent Y is in the intent queue waiting for lock L2 to be released by Intent X.
- Neither runs; the queue does not progress.

Without detection and resolution, these scenarios cause the platform to silently stall. The TTL on locks (ADR 0153) provides a backstop: locks expire after 10 minutes, eventually breaking the deadlock. But a 10-minute stall in an incident response scenario is unacceptable.

A dedicated deadlock detector with active resolution provides:
- **Fast detection**: deadlocks are detected within 30 seconds of formation.
- **Targeted resolution**: only the lower-priority agent is aborted; the higher-priority one continues.
- **Root cause visibility**: the deadlock cycle is recorded in the ledger and visible in the coordination map.

## Decision

We will implement a **distributed deadlock detector** as a periodic Windmill workflow that scans the lock registry and intent queue for cycle formation, and a **resolution protocol** that aborts the lowest-priority participant in the cycle.

The first repository implementation lands in [`platform/locking/deadlock_detector.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/locking/deadlock_detector.py) plus the Windmill wrapper [`config/windmill/scripts/detect-deadlocks.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/windmill/scripts/detect-deadlocks.py). It operates over the worker-shared lock registry, intent queue, and coordination map files seeded in the repo checkout and is scheduled every 30 seconds through the existing Windmill runtime role.

### Wait-for graph construction

A deadlock is a cycle in the **wait-for graph**: a directed graph where an edge from node A to node B means "agent A is waiting for a resource held by agent B."

```python
# platform/locking/deadlock_detector.py

def build_wait_for_graph() -> nx.DiGraph:
    """
    Build the wait-for graph from the current lock registry and intent queue state.
    """
    graph = nx.DiGraph()

    # Get all lock holders and waiters from the NATS JetStream KV
    locks = lock_registry.read_all()
    queue = intent_queue.read_waiting()

    for lock in locks:
        # For each lock that is held:
        for intent in queue:
            # If a queued intent is waiting for this resource:
            if lock.resource_path in intent.required_locks:
                # Add edge: intent waits for the agent holding the lock
                graph.add_edge(
                    node=f"intent:{intent.intent_id}",
                    to=f"agent:{lock.holder}",
                    resource=lock.resource_path,
                )

    # Include agent → resource → agent chains for held cross-resource locks
    for agent_session in coordination_map.read_all():
        if agent_session.status == "blocked" and agent_session.blocked_reason.startswith("waiting_for:"):
            blocked_on_resource = agent_session.blocked_reason.replace("waiting_for:", "")
            holder = lock_registry.get_holder(blocked_on_resource)
            if holder:
                graph.add_edge(
                    node=f"agent:{agent_session.context_id}",
                    to=f"agent:{holder}",
                    resource=blocked_on_resource,
                )

    return graph
```

### Cycle detection

```python
def detect_deadlocks(graph: nx.DiGraph) -> list[list[str]]:
    """Returns a list of cycles (each cycle is a list of node IDs forming the loop)."""
    try:
        cycles = list(nx.simple_cycles(graph))
        return [c for c in cycles if len(c) >= 2]
    except nx.NetworkXNoCycle:
        return []
```

### Resolution protocol

For each detected cycle, the resolver identifies the **lowest-priority participant** and aborts it:

```python
def resolve_deadlock(cycle: list[str]) -> DeadlockResolution:
    # Collect all agents in the cycle with their intent priorities
    participants = []
    for node in cycle:
        if node.startswith("agent:"):
            context_id = node.replace("agent:", "")
            session = coordination_map.read(context_id)
            intent = execution_intents.get(session.current_intent_id)
            participants.append(Participant(
                context_id=context_id,
                agent_id=session.agent_id,
                priority=intent.priority if intent else 50,
                intent_id=session.current_intent_id,
            ))

    # Lowest priority (highest numeric value) loses
    victim = max(participants, key=lambda p: p.priority)

    # Abort the victim's current intent
    resolution_action = abort_agent_intent(victim)

    return DeadlockResolution(
        cycle=cycle,
        victim=victim,
        survivors=[p for p in participants if p != victim],
        resolution_action=resolution_action,
    )
```

### Abort procedure

Aborting the victim's intent:

```python
def abort_agent_intent(victim: Participant) -> str:
    # 1. Cancel the Windmill job if it is running
    windmill.cancel_job(job_id=execution_intents.get_windmill_job_id(victim.intent_id))

    # 2. Release all locks held by the victim
    lock_registry.release_all(holder=f"agent:{victim.context_id}")

    # 3. Write abort event to ledger
    ledger.write(
        event_type="execution.deadlock_aborted",
        intent_id=victim.intent_id,
        metadata={
            "deadlock_cycle": deadlock_cycle,
            "aborted_by": "deadlock_detector",
            "survivors": [s.context_id for s in survivors],
        }
    )

    # 4. Re-queue the aborted intent with a delay (let winners finish first)
    intent_queue.enqueue(
        intent_id=victim.intent_id,
        priority=victim.priority,
        delay_seconds=60,
        reason="deadlock_resolution_retry",
    )

    # 5. Notify the victim agent via its NATS channel
    nats.publish(
        f"platform.agent.deadlock_notification.{victim.context_id}",
        {
            "type": "deadlock_aborted",
            "intent_id": str(victim.intent_id),
            "reason": "Aborted as lowest-priority participant in a deadlock cycle.",
            "retry_queued": True,
            "retry_delay_seconds": 60,
        }
    )

    return "aborted_and_requeued"
```

### Scheduler: run every 30 seconds

```python
# config/windmill/flows/deadlock-detector.yaml (Windmill recurring flow)
schedule: "*/30 * * * * *"   # Every 30 seconds (cron with seconds)
steps:
  - id: build_wait_for_graph
    type: script
    path: f/platform/locking/build_wait_for_graph

  - id: detect_cycles
    type: script
    path: f/platform/locking/detect_cycles
    args:
      graph: "{{ steps.build_wait_for_graph.result }}"

  - id: resolve_deadlocks
    type: forloop
    items: "{{ steps.detect_cycles.result }}"
    condition: "{{ len(steps.detect_cycles.result) > 0 }}"
    step:
      type: script
      path: f/platform/locking/resolve_deadlock
      args:
        cycle: "{{ item }}"
```

### Livelock detection

A livelock is a scenario where no deadlock exists but progress is still zero: agents are repeatedly aborting and re-queuing each other without any intent completing.

The detector also scans for livelocks by querying the intent queue for intents with `attempts > 3`:

```python
def detect_livelocks(queue: list[QueuedIntent]) -> list[QueuedIntent]:
    return [i for i in queue if i.attempts > 3 and (now() - i.queued_at).seconds > 300]
```

Livelocked intents are flagged in the coordination map and a `platform.findings.livelock_detected` finding is emitted to the triage engine. Unlike deadlocks, livelocks require operator review before resolution; the detector does not auto-resolve them.

### Metrics and alerting

| Metric | Alert threshold |
|---|---|
| `platform.deadlocks.detected_total` | > 0 in any 5-minute window → HIGH finding |
| `platform.deadlocks.resolution_failed_total` | > 0 → CRITICAL finding (abort failed) |
| `platform.livelocks.detected_total` | > 0 → MEDIUM finding (requires operator review) |
| Average lock wait time (`p95`) | > 60s → MEDIUM finding (contention high) |

## Consequences

**Positive**

- Deadlocks are detected within 30 seconds (two detector cycles) instead of waiting for the 10-minute lock TTL to expire. An incident response that deadlocks is unblocked within 30 seconds rather than 10 minutes.
- The wait-for graph is a precise record of the deadlock cycle, enabling post-incident analysis of why it formed and how to restructure agent interactions to prevent recurrence.
- Aborted intents are automatically re-queued rather than dropped. The agent does not need to manually retry; it receives a notification and the queue handles the retry after the survivors complete.

**Negative / Trade-offs**

- The wait-for graph construction reads the lock registry and intent queue every 30 seconds. This is a read-heavy operation on the NATS KV and Postgres queue. At scale (many concurrent agents), this could be a performance concern. The 30-second cycle can be tuned to 60 seconds for lower overhead at the cost of slower detection.
- The victim selection (lowest priority) is simple and correct for most scenarios but may produce counterintuitive results in some cases (e.g., a background maintenance task with priority 80 might be aborted in favour of keeping a slightly higher priority task that happens to be a non-urgent drift fix). The priority scale (ADR 0155) must be calibrated carefully to ensure incident response tasks always win.
- The livelock detector emits a finding but does not auto-resolve. An operator must intervene. If the operator is unavailable (late night), a livelock could persist until the next operator session. The handoff protocol (ADR 0131) should be configured to escalate livelock findings to an on-call path.

## Boundaries

- The deadlock detector operates on platform agent locks and intent queues. It does not detect deadlocks inside applications (e.g., Postgres row-level locks in the application database — those are managed by Postgres itself via `lock_timeout`).
- Livelock detection is advisory. Auto-resolution of livelocks is not implemented; it requires understanding the semantic reason agents are cycling, which is a judgment call.

## Related ADRs

- ADR 0044: Windmill (deadlock detector runs as a recurring Windmill flow)
- ADR 0058: NATS event bus (deadlock notification published to victim agent)
- ADR 0115: Event-sourced mutation ledger (execution.deadlock_aborted events)
- ADR 0124: Platform event taxonomy (platform.deadlocks.* events and findings)
- ADR 0126: Observation-to-action closure loop (livelock findings enter triage)
- ADR 0131: Multi-agent handoff protocol (livelock escalation to operator)
- ADR 0153: Distributed resource lock registry (lock holders/waiters used for wait-for graph)
- ADR 0154: VM-scoped execution lanes (lane holders included in wait-for graph)
- ADR 0155: Intent queue (queue waiters included in wait-for graph; aborted intents re-queued)
- ADR 0161: Real-time agent coordination map (deadlock status written to session entry)
