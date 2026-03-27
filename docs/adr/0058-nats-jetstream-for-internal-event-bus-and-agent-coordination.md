# ADR 0058: NATS JetStream For Internal Event Bus And Agent Coordination

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

As the platform adds more automation surfaces, event flow will otherwise become a mix of:

- direct webhooks
- polling loops
- email triggers
- ad hoc HTTP callbacks between services

That model is fragile for agentic coordination and difficult to observe over time.

## Decision

We will use NATS JetStream as the internal event-distribution backbone for control-plane and agent-oriented events.

Initial event categories:

1. workflow requested, started, succeeded, and failed
2. alert raised, acknowledged, and resolved
3. receipt recorded and verification completed
4. agent observation, recommendation, and approval-request events
5. future service-domain events that need reliable fan-out

Steady-state expectations:

- event subjects are named and documented
- publishers and consumers use scoped identities
- replay and retention are deliberate, not accidental
- internal-only publication is the default

## Consequences

- Agents and applications gain a durable event plane instead of bespoke webhook webs.
- Operational timelines become easier to reconstruct when several systems interact.
- Event contracts need governance so subjects and payloads do not sprawl.
- JetStream becomes another critical stateful control-plane component.

## Boundaries

- JetStream is not a replacement for PostgreSQL, receipts, or long-term document storage.
- Public publication of internal event subjects is out of scope.
- We do not need every service to move to the event bus before the first rollout is useful.
