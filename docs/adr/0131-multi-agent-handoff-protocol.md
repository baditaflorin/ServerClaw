# ADR 0131: Multi-Agent Handoff Protocol

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.122.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The platform now has several agent-facing automation surfaces, but they still tend to communicate implicitly:

- the triage engine can identify a likely remediation path, but it cannot formally transfer ownership of the next step
- long-running runbook automation can reach a failure boundary, but it lacks a structured operator escalation payload
- interactive sessions can decide that another agent should continue watching or investigating a task, but there is no durable handoff record

That gap makes coordination brittle. Operators end up rephrasing the same task in Mattermost or reopening the same incident context in a new session. Ownership changes are visible only in chat or in a sequence of loosely-related workflow receipts.

## Decision

We will implement a repository-managed handoff protocol with four concrete surfaces:

1. A typed `platform.handoff` package for creating, recording, routing, and completing handoffs.
2. A durable `handoff.transfers` schema for the canonical transfer record.
3. Mutation-ledger events that make each ownership transition auditable.
4. An operator CLI surface, `lv3 handoff`, for listing, accepting, refusing, and completing handoffs.

The protocol keeps the canonical transport subject name `platform.agent.handoff`, but the runtime is transport-agnostic. The repository implementation ships an in-memory transport used by tests and local orchestration; a NATS-backed adapter can plug into the same contract later without changing the handoff record format.

### Handoff message

```python
@dataclass
class HandoffMessage:
    handoff_id: str
    from_agent: str
    to_agent: str
    task_id: str
    subject: str
    payload: dict
    handoff_type: str           # delegate | escalate | inform
    requires_accept: bool
    timeout_seconds: int
    fallback: str               # operator | close | retry_self
    context_id: str | None
    reply_subject: str | None
    max_retries: int
    backoff_seconds: int
```

### Handoff response

```python
@dataclass
class HandoffResponse:
    handoff_id: str
    from_agent: str
    to_agent: str
    decision: str               # accept | refuse
    reason: str | None
    estimated_completion_seconds: int | None
```

### Durable state

Repository migration `migrations/0015_handoff_schema.sql` creates `handoff.transfers` with:

- sender and recipient identities
- shared `task_id`
- message body and routing metadata
- acceptance and completion status fields
- response reason and operator ETA fields

### Ledger events

The handoff subsystem writes these event types to the mutation ledger when a ledger sink is configured:

- `handoff.transfer_recorded`
- `handoff.accepted`
- `handoff.refused`
- `handoff.timed_out`
- `handoff.escalated_to_operator`
- `handoff.closed_unaccepted`
- `handoff.completed`

### CLI

The `lv3` CLI now exposes:

```bash
lv3 handoff send ...
lv3 handoff list ...
lv3 handoff view <handoff-id>
lv3 handoff accept <handoff-id>
lv3 handoff refuse <handoff-id> --reason ...
lv3 handoff complete <handoff-id> --actor ...
```

This gives operators and other automation a stable repo-managed surface even when the recipient is a human rather than a subscribed agent.

## Consequences

**Positive**

- Ownership transfer is explicit and durable instead of being inferred from chat history.
- Operators receive a structured escalation payload that can be accepted or refused later without losing the original task context.
- The protocol is load-tested in-repo with concurrent handoff bursts rather than being specified only in prose.
- Future transports can reuse the same message and persistence model.

**Negative / Trade-offs**

- The repository implementation stops at the transport boundary. A live NATS subscriber still has to be wired in when the surrounding ADR 0124/0125/0130 surfaces are integrated.
- `fallback=retry_self` is represented as a closed transfer with fallback metadata; the sender resumes work, but the transfer is still considered unaccepted.
- Operator notification is webhook-driven when configured; without a webhook, the durable record still exists but delivery depends on a caller polling or listing handoffs.

## Boundaries

- This ADR governs handoff creation, persistence, and acceptance. It does not execute the delegated task.
- The protocol does not replace the mutation ledger; it emits higher-level ownership transitions into it.
- The repository implementation is transport-agnostic and does not require live NATS to function in tests or local workflows.

## Implementation

The repository implementation is now present in:

- `platform/handoff/`
- `migrations/0015_handoff_schema.sql`
- `config/ledger-event-types.yaml`
- `scripts/lv3_cli.py`
- `tests/unit/test_handoff_protocol.py`
- `tests/test_lv3_cli.py`
- `docs/runbooks/agent-handoff-protocol.md`

## Related ADRs

- ADR 0044: Windmill
- ADR 0057: Mattermost ChatOps
- ADR 0058: NATS JetStream
- ADR 0090: Platform CLI
- ADR 0115: Event-sourced mutation ledger
