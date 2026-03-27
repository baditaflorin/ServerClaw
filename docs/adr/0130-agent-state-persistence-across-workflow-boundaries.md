# ADR 0130: Agent State Persistence Across Workflow Boundaries

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.122.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

Windmill (ADR 0044) is a stateless workflow executor. Every job starts with fresh state: the inputs passed at invocation time, the secrets available from OpenBao (ADR 0043), and the platform APIs the job can call. When a job completes or is interrupted, its in-memory state is gone.

For short, single-shot workflows, statelessness is a feature. For longer-horizon agentic work, it is a liability:

- a triage agent that wants to continue a hypothesis across two Windmill job boundaries currently has to rediscover its prior work
- arbitrary agent state has nowhere to live outside special-purpose tables
- an interrupted interactive agent session loses its intermediate reasoning and queued questions
- there is no generic way for one workflow to hand state to the next and verify the recipient resumed from the same snapshot

What is needed is a lightweight, general-purpose state store keyed by agent identity and logical task identifier, with short TTLs and an integrity check that survives workflow handoff boundaries.

## Decision

We will implement an **agent state store** in Postgres, accessible via a thin `AgentStateClient` API. The store is a scratchpad for in-progress agentic work, not a permanent database.

### Store schema

```sql
CREATE TABLE agent.state (
    state_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           JSONB NOT NULL,
    context_id      UUID,
    written_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX agent_state_uq_idx ON agent.state (agent_id, task_id, key);
CREATE INDEX agent_state_expiry_idx   ON agent.state (expires_at);
```

The repository implementation lives in:

- `migrations/0015_agent_state_schema.sql`
- `platform.agent.AgentStateClient`
- `lv3 agent state show|delete|verify`

### Client API

```python
from platform.agent import AgentStateClient

state = AgentStateClient(agent_id="agent/triage-loop", task_id="incident:inc-2026-03-24-001")
state.write("hypothesis.1", {"id": "recent-deployment", "confidence": 0.85})
state.read("hypothesis.1")
state.read_all()
state.delete("hypothesis.1")
checkpoint = state.checkpoint({"resume_at": "verify-health"})
state.validate_handoff(checkpoint["state_digest"])
```

### TTL and size model

- default TTL: 24 hours unless the caller supplies a shorter or longer TTL
- max value size: 64 KB per key
- max active keys: 100 per `(agent_id, task_id)` namespace
- expired state is invisible to normal reads and can be purged by maintenance automation

### Handoff integrity validation

`checkpoint()` computes a SHA-256 `state_digest` over the active key/value set and publishes `platform.agent.state_checkpoint` when a NATS URL is configured. A downstream workflow can call `validate_handoff(expected_digest)` or `lv3 agent state verify` after reading the same task namespace. If the digest differs, the recipient is not looking at the same active state snapshot the sender checkpointed.

## Consequences

**Positive**

- agents can persist in-progress hypotheses and queued follow-up actions across workflow boundaries
- operators can inspect or delete scratch state through the CLI instead of ad hoc SQL
- downstream workflows can verify state integrity after handoff before resuming work
- strict TTL, size, and key-count limits keep the store in the scratchpad domain

**Negative / Trade-offs**

- the store is still ephemeral scratch state, not the permanent record of truth
- callers are responsible for handling version conflicts when they write through a stale client view
- digest verification only proves snapshot equality for the active key set; it does not replace a full handoff protocol

## Boundaries

- resolved findings and completed actions still belong in the mutation ledger or failure-case library
- the state store is not a shared memory space for arbitrary browsing; callers need the relevant `agent_id` and `task_id`
- this ADR defines the persistence mechanism, not what each agent should choose to persist

## Related ADRs

- ADR 0043: OpenBao for secrets
- ADR 0044: Windmill stateless workflow execution
- ADR 0090: Platform CLI
- ADR 0098: Postgres HA
- ADR 0115: Event-sourced mutation ledger
