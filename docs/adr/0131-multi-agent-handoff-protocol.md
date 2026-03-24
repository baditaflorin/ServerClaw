# ADR 0131: Multi-Agent Handoff Protocol

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform has multiple agent identities that operate with different specialisations:

- `agent/triage-loop`: activated on every alert; correlates signals and ranks hypotheses.
- `agent/observation-loop`: scheduled 4-hourly; detects drift and health deviations.
- `agent/runbook-executor`: drives multi-step runbook execution (ADR 0129).
- `agent/claude-code`: interactive Claude Code sessions initiated by an operator.

These agents currently operate in isolation. The triage engine fires and produces a report, but it has no mechanism to delegate follow-up work to the runbook executor. The observation loop surfaces a finding, but it cannot assign the follow-up to the triage loop. An interactive Claude Code session cannot formally hand off a long-running task to an autonomous agent when the operator wants to step away.

The consequence is that multi-agent scenarios require manual orchestration: a Mattermost message from the triage engine is read by an operator who then manually triggers the runbook executor. This is the same manual handoff gap that the closure loop (ADR 0126) is designed to eliminate — but the closure loop only manages the observation-to-action transition. A full multi-agent scenario (triage → investigate → execute → verify → update case) with different agent identities at each stage has no coordination protocol.

What is missing is a **handoff protocol**: a typed message format, a NATS delivery contract, and a ledger record that governs the transfer of task ownership from one agent to another, with explicit acceptance, refusal, and timeout handling.

## Decision

We will define a **multi-agent handoff protocol** using the canonical NATS event topic `platform.agent.handoff` (ADR 0124) with exactly-once delivery semantics, backed by a `handoff.transfers` Postgres table for durability and audit.

### Handoff message structure

```python
@dataclass
class HandoffMessage:
    handoff_id:      str          # UUID; used for exactly-once dedup in NATS
    from_agent:      str          # Sender agent_id
    to_agent:        str          # Recipient agent_id (or 'operator' for human escalation)
    task_id:         str          # Shared task identifier (ADR 0130 state namespace)
    context_id:      str          # SessionContext from bootstrap (ADR 0123)
    subject:         str          # One-line description of the delegated task
    payload:         dict         # Task-specific data (findings, hypotheses, params)
    handoff_type:    str          # 'delegate' | 'escalate' | 'inform'
    requires_accept: bool         # If True, sender waits for acceptance before proceeding
    timeout_seconds: int          # Time to wait for acceptance before fallback
    fallback:        str          # 'operator' | 'close' | 'retry_self'
    reply_subject:   str | None   # NATS reply subject for accept/refuse response
```

### Handoff types

| Type | Semantics | Requires accept |
|---|---|---|
| `delegate` | Sender transfers task ownership to recipient; sender blocks or moves on based on `requires_accept` | Optional |
| `escalate` | Sender cannot proceed; human operator (or higher-trust agent) must take over | Always True |
| `inform` | Fire-and-forget notification; sender does not wait for acknowledgement | Always False |

### Wire protocol

1. **Sender** compiles a `HandoffMessage` and publishes it to `platform.agent.handoff` with the NATS `handoff_id` as the deduplication key.
2. **Recipient** subscribes to `platform.agent.handoff` filtered by `to_agent == self.agent_id`. On receipt:
   - Reads the task state from the agent state store (ADR 0130) using the `task_id`.
   - Evaluates whether it can accept (capability check via ADR 0125).
   - If `requires_accept`, publishes an `accept` or `refuse` response to `reply_subject`.
3. **Sender** receives the accept/refuse (or times out). On timeout, applies `fallback` strategy.
4. Both sender and recipient write `handoff.transfer_recorded` events to the ledger (ADR 0115).

### Acceptance and refusal

```python
@dataclass
class HandoffResponse:
    handoff_id:   str
    from_agent:   str    # Responder
    to_agent:     str    # Original sender
    decision:     str    # 'accept' | 'refuse'
    reason:       str | None
    estimated_completion_seconds: int | None  # Informational
```

A `refuse` response with `reason: 'capability_exceeded'` triggers the `fallback` path immediately. A `refuse` with `reason: 'busy'` triggers a configurable retry: the sender waits `backoff_seconds` and re-sends the handoff up to `max_retries` times.

### Fallback strategies

| Fallback | Behaviour |
|---|---|
| `operator` | Publish to Mattermost; write `handoff.escalated_to_operator` ledger event |
| `close` | Abandon the task; write `handoff.closed_unaccepted` ledger event |
| `retry_self` | Sender re-assumes the task and continues with its own capabilities |

### Durability table

```sql
CREATE TABLE handoff.transfers (
    handoff_id          UUID PRIMARY KEY,
    from_agent          TEXT NOT NULL,
    to_agent            TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    context_id          UUID,
    handoff_type        TEXT NOT NULL,
    subject             TEXT NOT NULL,
    payload             JSONB NOT NULL,
    status              TEXT NOT NULL,  -- 'pending' | 'accepted' | 'refused' | 'timed_out' | 'completed'
    requires_accept     BOOLEAN NOT NULL,
    timeout_seconds     INTEGER NOT NULL,
    fallback            TEXT NOT NULL,
    sent_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at        TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    response_decision   TEXT,
    response_reason     TEXT
);

CREATE INDEX handoff_transfers_to_idx      ON handoff.transfers (to_agent, status);
CREATE INDEX handoff_transfers_task_idx    ON handoff.transfers (task_id);
```

### Canonical handoff patterns

**Pattern 1: Triage → Runbook executor**

```python
# agent/triage-loop, after ranking hypothesis 'tls-cert-expiry' with confidence=0.92
handoff = HandoffMessage(
    from_agent="agent/triage-loop",
    to_agent="agent/runbook-executor",
    task_id=f"incident:{incident_id}",
    subject="Execute runbook: renew-tls-certificate for step-ca",
    payload={
        "runbook_id": "renew-tls-certificate",
        "params": {"service": "step-ca"},
        "triage_hypothesis": "tls-cert-expiry",
        "confidence": 0.92,
    },
    handoff_type="delegate",
    requires_accept=False,   # Fire and observe; triage loop moves on
    fallback="operator",
)
HandoffClient().send(handoff)
```

**Pattern 2: Runbook executor → Operator (escalation)**

```python
# agent/runbook-executor, step 'verify-health' failed twice
handoff = HandoffMessage(
    from_agent="agent/runbook-executor",
    to_agent="operator",
    task_id=f"runbook-run:{run_id}",
    subject="Runbook renew-tls-certificate: health verification failed after renewal",
    payload={
        "run_id": run_id,
        "failed_step": "verify-health",
        "step_result": {"status": "degraded", "probe_error": "connection refused"},
        "state_link": f"lv3 agent state show --task runbook-run:{run_id}",
    },
    handoff_type="escalate",
    requires_accept=True,
    timeout_seconds=3600,    # 1 hour for operator to respond
    fallback="close",
)
```

**Pattern 3: Claude Code session → Observation loop (background monitoring)**

```python
# operator/live, finishing an interactive session
handoff = HandoffMessage(
    from_agent="agent/claude-code",
    to_agent="agent/observation-loop",
    task_id="operator-session:live-20260324",
    subject="Monitor netbox over next 4 hours for deployment regression",
    payload={
        "watch_service": "netbox",
        "watch_for": ["health_probe_failing", "error_log_spike"],
        "alert_threshold": "any_signal_above_warning",
        "context": "Deployment completed 10 minutes ago; operator stepping away",
    },
    handoff_type="delegate",
    requires_accept=True,
    timeout_seconds=60,
    fallback="operator",
)
```

### Platform CLI

```bash
$ lv3 handoff list --task incident:inc-2026-03-24-netbox-001
HANDOFF_ID   FROM                   TO                     TYPE      STATUS     AGE
abc-001      agent/triage-loop      agent/runbook-executor delegate  accepted   5m
abc-002      agent/runbook-executor operator               escalate  pending    2m

$ lv3 handoff accept abc-002     # Operator accepts the runbook executor escalation
$ lv3 handoff view abc-001
```

## Consequences

**Positive**

- Task ownership is explicit and auditable. The ledger and `handoff.transfers` table record exactly which agent held a task at each point in its lifecycle.
- Escalation to an operator follows a structured path: the handoff message includes the task state link, the failed step, and the context needed to resume work. Operators do not receive "automation failed" with no context.
- The exactly-once NATS delivery guarantee prevents duplicate task delegation (two runbook executors racing on the same handoff).
- The fallback model ensures no task is silently dropped: every handoff that is not accepted within its timeout either escalates to an operator or writes a `closed_unaccepted` ledger event.

**Negative / Trade-offs**

- The protocol introduces round-trip latency for `requires_accept: true` handoffs. If the recipient is slow to start (Windmill job cold start), the sender blocks for up to `timeout_seconds`.
- Agent identities that are not running (e.g., `agent/runbook-executor` has no active Windmill subscription) will not accept handoffs, triggering fallback paths. The platform must ensure critical agent subscriptions are always active or have reliable startup paths.
- The `platform.agent.handoff` topic uses exactly-once delivery, which requires NATS JetStream with deduplication configured correctly. Mis-configuration can result in duplicate handoffs being delivered.

## Boundaries

- The handoff protocol governs task ownership transfer between agent identities. It does not govern the execution of the delegated task; that remains the recipient's responsibility using its own tools.
- Handoffs to `to_agent: 'operator'` are implemented as Mattermost notifications (ADR 0057) with an ops portal deep link (ADR 0093). They are not NATS-delivered.
- This ADR defines the protocol. The specific handoffs that each agent type sends and accepts are defined in the respective agent ADRs (ADR 0114, ADR 0071, ADR 0129).

## Related ADRs

- ADR 0044: Windmill (agent runtime)
- ADR 0046: Identity classes (agent_id field)
- ADR 0057: Mattermost ChatOps (operator handoff delivery)
- ADR 0058: NATS JetStream (exactly-once delivery for platform.agent.handoff)
- ADR 0071: Agent observation loop (sends inform handoffs; receives delegate from Claude Code)
- ADR 0090: Platform CLI (`lv3 handoff` commands)
- ADR 0093: Interactive ops portal (operator handoff acceptance UI)
- ADR 0114: Rule-based incident triage engine (sends delegate to runbook-executor)
- ADR 0115: Event-sourced mutation ledger (handoff events recorded)
- ADR 0123: Agent session bootstrap (context_id included in handoff)
- ADR 0124: Platform event taxonomy (platform.agent.handoff topic)
- ADR 0125: Agent capability bounds (recipient checks capability before accepting)
- ADR 0129: Runbook automation executor (primary recipient of triage delegate handoffs)
- ADR 0130: Agent state persistence (task_id shared state read by recipient after handoff)
