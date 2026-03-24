# ADR 0130: Agent State Persistence Across Workflow Boundaries

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Windmill (ADR 0044) is a stateless workflow executor. Every job starts with fresh state: the inputs passed at invocation time, the secrets available from OpenBao (ADR 0043), and the platform APIs the job can call. When a job completes or is interrupted, its in-memory state is gone.

For short, single-shot workflows — "deploy netbox", "rotate a secret", "check certificate expiry" — statelessness is a feature. Idempotency is easy to reason about when there is no accumulated state to worry about.

For longer-horizon agentic work, statelessness is a liability:

- A triage agent that identifies a hypothesis, runs a discriminating check, finds it inconclusive, and wants to try a second hypothesis across two Windmill job boundaries currently has no way to pass the first hypothesis's findings to the second job without re-running the first.
- The closure loop (ADR 0126) maintains a `loop.runs` record in Postgres, but this is loop-specific. Arbitrary agent state — partial findings, hypotheses under investigation, questions queued for the next operator session — has nowhere to live.
- An interactive Claude Code session that is interrupted (network drop, context window limit, operator pause) loses all intermediate reasoning. When the session resumes, the agent must re-discover state from scratch.
- The runbook executor (ADR 0129) stores step results in `runbook.runs`, but a general-purpose agent working across multiple runbooks and ad hoc tool calls has no equivalent.

What is needed is a lightweight, general-purpose state store that any agent identity can write to and read from, keyed by agent identity and a logical task identifier, with a short TTL to prevent stale state from accumulating.

## Decision

We will implement an **agent state store** in Postgres, accessible via a thin `AgentStateClient` API. The store is explicitly not a general-purpose database: it is a scratchpad for in-progress agentic work, with strict TTLs and a small per-entry size limit.

### Store schema

```sql
CREATE TABLE agent.state (
    state_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,           -- Identity from ADR 0046
    task_id         TEXT NOT NULL,           -- Logical task (e.g., 'incident:inc-2026-03-24-001')
    key             TEXT NOT NULL,           -- State key within the task
    value           JSONB NOT NULL,
    context_id      UUID,                    -- SessionContext that created this entry (ADR 0123)
    written_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,    -- Mandatory TTL; no immortal state entries
    version         INTEGER NOT NULL DEFAULT 1  -- Optimistic lock; incremented on update
);

CREATE UNIQUE INDEX agent_state_uq_idx ON agent.state (agent_id, task_id, key);
CREATE INDEX agent_state_expiry_idx   ON agent.state (expires_at);
```

A background cron job purges expired rows daily.

### Client API

```python
# platform/agent/state.py

class AgentStateClient:
    def __init__(self, agent_id: str, task_id: str, default_ttl_hours: int = 24):
        ...

    def write(self, key: str, value: Any, ttl_hours: int | None = None) -> None:
        """Write or overwrite a state entry. Max value size: 64 KB."""

    def read(self, key: str, default: Any = None) -> Any:
        """Read a state entry. Returns default if not found or expired."""

    def read_all(self) -> dict[str, Any]:
        """Read all non-expired entries for this agent/task combination."""

    def delete(self, key: str) -> None:
        """Explicitly delete a state entry."""

    def checkpoint(self, state: dict) -> None:
        """Atomically write multiple keys and publish platform.agent.state_checkpoint to NATS."""
```

### TTL model

Every state entry requires an explicit TTL at write time. Default TTLs by entry type:

| Entry type | Default TTL | Rationale |
|---|---|---|
| `hypothesis.*` | 4 hours | Triage hypotheses are stale after one observation cycle |
| `in_progress_task.*` | 24 hours | Active tasks; expire if not resolved within a day |
| `question_queue.*` | 72 hours | Questions for the next operator session |
| `context_summary.*` | 1 hour | Cached context; re-hydrate from bootstrap instead |

There is no mechanism to extend a TTL indefinitely. Agents that need longer-lived state must write to the case library (ADR 0118) for resolved findings or the ledger (ADR 0115) for completed actions.

### Task identifier convention

The `task_id` field is a free-form string but should follow the convention `<domain>:<identifier>`:

```
incident:inc-2026-03-24-netbox-001
runbook-run:run-abc-123
observation-cycle:2026-03-24T14:00:00Z
operator-session:live-20260324
```

Multiple agent identities working on the same `task_id` (e.g., a triage agent and a runbook executor both operating on the same incident) can share state by reading each other's keys within the same task namespace.

### Usage patterns

**Pattern 1: Multi-step triage across Windmill job boundaries**

```python
# Job 1: Initial triage
state = AgentStateClient(agent_id="agent/triage-loop", task_id=f"incident:{incident_id}")
state.write("hypothesis_1", {"id": "recent-deployment", "confidence": 0.85, "evidence": [...]})
state.write("checked_hypotheses", ["recent-deployment"])

# Job 2: Follow-up discriminating check (triggered by closure loop)
state = AgentStateClient(agent_id="agent/triage-loop", task_id=f"incident:{incident_id}")
prior = state.read("hypothesis_1")
already_checked = state.read("checked_hypotheses", default=[])
# ... continue from where Job 1 left off
```

**Pattern 2: Queuing questions for an operator session**

```python
# Autonomous agent accumulates questions it cannot answer alone
state = AgentStateClient(agent_id="agent/claude-code", task_id="operator-session:live-20260324")
state.write("question_queue.1", {
    "question": "Should I rotate the netbox DB password before or after the maintenance window?",
    "context": {"service": "netbox", "upcoming_window": "2026-03-25T02:00Z"},
}, ttl_hours=72)
```

**Pattern 3: Checkpoint for resumable long-running work**

```python
# Runbook executor checkpoints after each step
state = AgentStateClient(agent_id="agent/runbook-executor", task_id=f"runbook-run:{run_id}")
state.checkpoint({
    "last_completed_step": "renew-cert",
    "step_results": {"check-expiry": {...}, "renew-cert": {...}},
    "resume_at": "verify-health",
})
# checkpoint() also publishes platform.agent.state_checkpoint to NATS (ADR 0124)
# so the closure loop knows the run is still in progress
```

### Size limits

- Maximum value size per key: 64 KB (JSONB).
- Maximum keys per (agent_id, task_id): 100.
- Values exceeding 64 KB must be written to the ledger or case library, not the state store.

These limits enforce the scratchpad contract. The state store is for in-progress coordination data, not for storing full artifacts.

### Platform CLI

```bash
$ lv3 agent state show --agent agent/triage-loop --task incident:inc-2026-03-24-netbox-001
key                    value                     written_at         expires_at
hypothesis_1           {confidence: 0.85, ...}   14:32:01Z          18:32:01Z
checked_hypotheses     ["recent-deployment"]      14:32:01Z          18:32:01Z

$ lv3 agent state delete --agent agent/triage-loop --task incident:inc-2026-03-24-netbox-001 --key hypothesis_1
```

## Consequences

**Positive**

- Agents working across multiple Windmill job boundaries no longer restart from scratch. Hypotheses, findings, and in-progress reasoning accumulate within a task scope rather than being discarded on each job completion.
- The shared task namespace lets multiple agent identities collaborate on the same incident without duplicating discovery work.
- Strict TTLs and size limits prevent the state store from becoming an informal secondary database. Permanent data must go to the ledger or case library.
- The `checkpoint()` method with NATS publishing (ADR 0124) gives the closure loop visibility into long-running agent progress without polling.

**Negative / Trade-offs**

- The state store is an eventually-consistent scratchpad, not a transactional database. Concurrent writes from two agents to the same key use optimistic locking (version field), but conflicts produce an error that the caller must handle rather than an automatic merge.
- Agents that fail to checkpoint intermediate state before a Windmill job timeout lose that state permanently. The platform cannot reconstruct in-memory state from external sources.
- The 24-hour maximum default TTL for in-progress tasks means that a task that genuinely spans multiple days (e.g., a multi-day incident investigation) will have its state expire. Operators must manually extend the TTL via the CLI or accept that the agent will rediscover state from the ledger and case library.

## Boundaries

- The agent state store is for ephemeral, in-progress coordination data only. Resolved findings, completed actions, and audit-relevant records must be written to the mutation ledger (ADR 0115) or case library (ADR 0118).
- Operators cannot read arbitrary agent state without the relevant `agent_id` and `task_id`. The state store is not a shared memory space accessible to all callers.
- This ADR does not define what agents should persist; it provides the mechanism. Individual agent implementations decide what is worth checkpointing.

## Related ADRs

- ADR 0043: OpenBao (secrets are never written to the state store; use OpenBao for secrets)
- ADR 0044: Windmill (stateless execution model that motivates this ADR)
- ADR 0046: Identity classes (agent_id field)
- ADR 0090: Platform CLI (`lv3 agent state` commands)
- ADR 0098: Postgres HA (backing store for agent.state table)
- ADR 0114: Rule-based incident triage engine (primary consumer pattern 1)
- ADR 0115: Event-sourced mutation ledger (permanent record destination for resolved findings)
- ADR 0118: Replayable failure case library (permanent record destination for completed cases)
- ADR 0123: Agent session bootstrap (context_id stored alongside state entries)
- ADR 0124: Platform event taxonomy (platform.agent.state_checkpoint published on checkpoint)
- ADR 0126: Observation-to-action closure loop (reads checkpoint events to track run progress)
- ADR 0129: Runbook automation executor (pattern 3: checkpointing between steps)
