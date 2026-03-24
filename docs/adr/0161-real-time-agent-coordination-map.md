# ADR 0161: Real-Time Agent Coordination Map

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

When multiple agents run concurrently, each agent bootstraps its session (ADR 0123) from a **snapshot** of platform state captured at `captured_at`. This snapshot is accurate at the moment of capture but becomes stale immediately as other agents act. An agent making a decision at T+5 minutes based on a snapshot from T+0 may be reasoning about a platform that has already changed.

Current real-time signals available to an agent during a session:
- The mutation ledger (ADR 0115): a stream of committed events. Useful for "what happened" but requires manual polling to learn "what is happening right now."
- The NATS event bus (ADR 0058): live events, but only those the agent subscribes to. An agent working on a specific task does not necessarily subscribe to events emitted by other agents working on unrelated tasks.
- The handoff protocol (ADR 0131): point-to-point agent communication for explicit handoffs. Not a general-purpose coordination mechanism.

What is missing is a **shared live view** of the entire multi-agent system's current state: what each agent is doing right now, what resources it holds, what its progress is, and whether it is healthy. Without this, agents are blind to each other except through the indirect signals of lock contention (ADR 0153) and intent conflicts (ADR 0127).

The consequence in practice:
- Agent A is executing a rolling restart of Keycloak. Agent B, having bootstrapped 3 minutes earlier, sees Keycloak as `healthy` in its snapshot. Agent B makes a decision that assumes Keycloak is fully responsive. The actual restart causes B's decision to fail in a way that is mysterious without context.
- Three agents are each waiting for the same lane (ADR 0154). None of them knows the others are waiting. Each independently decides to escalate to the operator, flooding `#platform-incidents` with three redundant alerts.
- An agent working on a long-running task is unaware that another agent has already resolved the same incident it is investigating, causing duplicate remediation.

The correct architecture is a **real-time coordination map**: a shared, low-latency, continuously-updated view of all active agent sessions and their current activity.

## Decision

We will implement a **real-time agent coordination map** backed by NATS JetStream Key-Value, providing a live per-session view accessible to all agents, operators, and the ops portal.

### Coordination map entry schema

```python
@dataclass
class AgentSessionEntry:
    # Identity
    context_id: UUID              # Session context (ADR 0123)
    agent_id: str                 # e.g., "agent/triage-loop"
    session_label: str            # Human-readable: "triage-loop session 2026-03-24T14:32:01"

    # Current activity
    current_phase: str            # "bootstrapping" | "planning" | "dry-running" | "executing" | "verifying" | "idle"
    current_intent_id: UUID       # If executing/verifying, which intent
    current_workflow_id: str      # If executing, which workflow
    current_target: str           # e.g., "service:netbox" | "vm:120" | "config/subdomain-catalog.json"

    # Resource holds
    held_locks: list[str]         # Resource lock paths (from ADR 0153)
    held_lanes: list[str]         # Lane IDs (from ADR 0154)
    reserved_budget: dict         # {cpu_milli, memory_mb, disk_iops}

    # Progress
    batch_id: UUID                # If part of a batch (ADR 0160)
    batch_stage: int              # Current stage in execution plan
    step_index: int               # Current step within workflow
    step_count: int               # Total steps in workflow
    progress_pct: float           # 0.0 - 1.0

    # Health
    last_heartbeat: datetime      # Agent must heartbeat every 30s; absence → stale
    status: str                   # "active" | "stale" | "blocked" | "escalated" | "completing"
    blocked_reason: str           # If blocked: what is it waiting for
    error_count: int              # Number of errors in this session

    # Timestamps
    started_at: datetime
    estimated_completion: datetime  # Updated as workflow progresses
    expires_at: datetime            # Session TTL
```

### NATS JetStream KV backing

```python
COORD_MAP_KV_BUCKET = "platform.agent_coordination"
COORD_MAP_TTL = 300  # 5 minutes; entries auto-expire if agent stops heartbeating

class AgentCoordinationMap:

    def publish(self, entry: AgentSessionEntry):
        """Publish/update this agent's session entry. Called on every state transition."""
        key = f"{entry.agent_id}/{entry.context_id}"
        self.kv.put(key, encode(entry))

    def read_all(self) -> list[AgentSessionEntry]:
        """Read all active session entries. Stale entries are expired by TTL."""
        return [decode(v) for v in self.kv.list_values()]

    def read_by_agent(self, agent_id: str) -> list[AgentSessionEntry]:
        return [e for e in self.read_all() if e.agent_id == agent_id]

    def read_by_target(self, target: str) -> list[AgentSessionEntry]:
        """Find all agents currently acting on a given resource."""
        return [e for e in self.read_all() if e.current_target == target]
```

### Agent heartbeat and state transitions

Agents call `coordination_map.publish()` on every phase transition:

```python
# platform/agent/session.py

class AgentSession:

    def transition(self, new_phase: str, **kwargs):
        self.entry.current_phase = new_phase
        self.entry.last_heartbeat = now()
        for key, value in kwargs.items():
            setattr(self.entry, key, value)
        coordination_map.publish(self.entry)
        # Also publish to NATS event bus for other agents' subscriptions
        nats.publish("platform.agent.state_updated", self.entry.__dict__)

    # Background heartbeat (every 30 seconds, even with no phase change)
    def _heartbeat_loop(self):
        while self._running:
            self.entry.last_heartbeat = now()
            coordination_map.publish(self.entry)
            time.sleep(30)
```

Phase transitions are fast (KV write latency < 5ms). Other agents reading the coordination map see updates within the NATS JetStream propagation latency (~10ms for a single-node deployment).

### Agent awareness of coordination map

Every agent session checks the coordination map at bootstrap and on key decision points:

```python
# In agent decision loop:

def should_escalate_to_operator(finding: Finding) -> bool:
    # Check if another agent is already working on the same finding
    agents_on_target = coordination_map.read_by_target(finding.service_id)
    already_handling = [
        a for a in agents_on_target
        if a.agent_id != self.agent_id
        and a.current_phase in ("executing", "verifying")
    ]
    if already_handling:
        # Another agent is already on this; don't escalate separately
        return False
    return True  # Only escalate if we're the one handling it
```

```python
# In lane scheduler (ADR 0154):

def find_agents_waiting_for_lane(lane_id: str) -> list[AgentSessionEntry]:
    """How many agents are blocked on this lane? Used to prioritise dispatch."""
    return [
        a for a in coordination_map.read_all()
        if a.status == "blocked"
        and lane_id in a.held_lanes
    ]
```

### Ops portal live view

The ops portal (ADR 0093) and Homepage dashboard (ADR 0152) render the coordination map as a live agent activity panel, refreshed via SSE:

```
┌─────────────────────────────────────────────────────────────────────┐
│ ACTIVE AGENTS                              2026-03-24 14:32:01     │
├──────────────────────────────────────────┬──────────────────────────┤
│ agent/triage-loop    [████████░░] 80%     │ Executing: restart-netbox│
│   Context: ctx:a1b2  Lane: docker-runtime │ Locks: vm:120/netbox     │
│   ETA: ~2m           Locks: 1  Errors: 0  │                          │
├──────────────────────────────────────────┤                          │
│ agent/observation-loop [██░░░░░░] 20%     │ Planning: rotate-grafana │
│   Context: ctx:c3d4  Lane: monitoring     │ Phase: dry-running       │
│   ETA: ~8m           Locks: 0  Errors: 0  │                          │
├──────────────────────────────────────────┤                          │
│ agent/claude-code    [idle]               │ Waiting for lane release │
│   Context: ctx:e5f6  BLOCKED              │ Blocked by: ctx:a1b2     │
│   Waiting: 45s       Queue pos: 1        │                          │
└──────────────────────────────────────────┴──────────────────────────┘
```

The "BLOCKED" status with a `Blocked by` pointer lets operators immediately understand why an agent is waiting and how long until it unblocks.

### Coordination map as conflict detection signal

The goal compiler (ADR 0112) consults the coordination map before acquiring locks:

```python
# In goal_compiler/compiler.py, before lock acquisition:
agents_on_target = coordination_map.read_by_target(intent.resource_path)
if agents_on_target:
    # Another agent is already acting on this target. Check if we conflict.
    conflict_risk = assess_coordination_conflict(intent, agents_on_target)
    if conflict_risk.severity == "HIGH":
        # Don't even attempt lock acquisition; go straight to intent queue
        return IntentResult(status="queued", reason=conflict_risk.reason)
```

This proactive check reduces the rate of lock contention (acquire → fail → retry) in favour of cooperative scheduling (see coordination map → choose to wait immediately).

## Consequences

**Positive**

- Duplicate escalation is eliminated: agents check the coordination map before escalating and defer if another agent is already handling the same target.
- Blocked agents are visible to operators with context on why they are blocked and when they will unblock, turning a confusing "agent is stuck" situation into a clear "agent is waiting for X" situation.
- The coordination map enables cooperative scheduling: agents that see a conflict coming consult the map and queue themselves before competing for a lock, reducing contention and improving throughput.

**Negative / Trade-offs**

- The coordination map is eventually consistent: a KV entry may be up to ~10ms stale. In the extreme edge case of two agents simultaneously reading "no one else is acting on service:netbox" and both proceeding, the lock registry (ADR 0153) remains the authoritative conflict resolver. The coordination map is a cooperative hint layer, not a replacement for locking.
- Agents must implement the heartbeat loop reliably. A bug that stops the heartbeat causes the coordination map entry to expire (5-minute TTL), making the agent invisible to others for up to 5 minutes.

## Boundaries

- The coordination map shows what agents are doing (active session state). It does not show historical activity (that is the mutation ledger, ADR 0115) or full session replay (that is the agent state store, ADR 0130).
- The coordination map is not used for agent authentication or authorisation. Lock registry and capability bounds checks are the authoritative controls.

## Related ADRs

- ADR 0058: NATS event bus (JetStream KV backing store; state_updated events)
- ADR 0093: Interactive ops portal (live agent activity panel)
- ADR 0112: Deterministic goal compiler (consults map before lock acquisition)
- ADR 0123: Agent session bootstrap (initial entry created on bootstrap)
- ADR 0124: Platform event taxonomy (platform.agent.state_updated events)
- ADR 0131: Multi-agent handoff protocol (handoff target chosen with coordination map context)
- ADR 0153: Distributed resource lock registry (authoritative; coordination map is cooperative)
- ADR 0154: VM-scoped execution lanes (lane scheduler reads coordination map for wait depth)
- ADR 0155: Intent queue (blocked agents appear in coordination map; dispatcher reads depth)
- ADR 0152: Homepage dashboard (agent activity panel)
