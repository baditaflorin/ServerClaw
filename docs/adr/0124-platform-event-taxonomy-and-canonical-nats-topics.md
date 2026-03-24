# ADR 0124: Platform Event Taxonomy and Canonical NATS Topics

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

NATS JetStream (ADR 0058) is the platform's internal event bus. It is used today for:

- Alert delivery from the alerting router (ADR 0097) to the triage engine (ADR 0114).
- Observation findings from the observation loop (ADR 0071) to the Mattermost bridge and GlitchTip.
- Control-plane communication between services (ADR 0045).

However, the topic names, payload shapes, and delivery guarantees used across these consumers are defined independently in each component. The observation loop publishes to `platform.findings.<check-name>`. The triage engine writes its output to the mutation ledger and posts to Mattermost, but does not publish a NATS event. The ledger writer (ADR 0115) does not currently fan out any events to NATS at all.

The result is that agents and automation that want to react to platform events — a deployment completing, an incident opening, drift being detected, a budget being exceeded — must poll the ledger or Mattermost rather than subscribing to a durable event stream. This is architecturally backwards: NATS exists precisely to enable reactive, event-driven flows without polling.

Without a canonical event taxonomy, every new subscriber must reverse-engineer the payload format from the producer's source code. Adding a new producer that emits events to an undocumented topic creates invisible consumers that break silently when the payload changes.

## Decision

We will define a **canonical platform event taxonomy** as a versioned configuration file (`config/event-taxonomy.yaml`) and enforce that all platform components that publish to NATS use only topics and payload shapes declared in the taxonomy. The taxonomy is the contract between producers and consumers.

### Topic structure

All platform topics follow the pattern:

```
platform.<domain>.<event-name>
```

Wildcards follow standard NATS convention: `platform.>` subscribes to all platform events; `platform.execution.*` subscribes to all execution-domain events.

### Canonical topic registry

```yaml
# config/event-taxonomy.yaml

version: "1.0"

domains:

  intent:
    description: Events produced by the goal compiler and approval gate
    topics:
      - name: platform.intent.compiled
        description: A natural-language instruction was compiled into an ExecutionIntent
        payload_schema: schemas/events/intent_compiled.json
        delivery: at_least_once
        retention: 7d
      - name: platform.intent.approved
        description: An ExecutionIntent passed the approval gate and was submitted to the scheduler
        payload_schema: schemas/events/intent_approved.json
        delivery: at_least_once
        retention: 7d
      - name: platform.intent.rejected
        description: An ExecutionIntent was rejected (approval gate, budget, or conflict)
        payload_schema: schemas/events/intent_rejected.json
        delivery: at_least_once
        retention: 7d

  execution:
    description: Events produced by the budgeted workflow scheduler and Windmill
    topics:
      - name: platform.execution.started
        description: A Windmill workflow job started
        payload_schema: schemas/events/execution_started.json
        delivery: at_least_once
        retention: 7d
      - name: platform.execution.completed
        description: A Windmill workflow job completed successfully
        payload_schema: schemas/events/execution_completed.json
        delivery: at_least_once
        retention: 7d
      - name: platform.execution.failed
        description: A Windmill workflow job failed
        payload_schema: schemas/events/execution_failed.json
        delivery: at_least_once
        retention: 7d
      - name: platform.execution.budget_exceeded
        description: A workflow hit a budget limit and was aborted
        payload_schema: schemas/events/execution_budget_exceeded.json
        delivery: at_least_once
        retention: 30d

  health:
    description: Events produced by health probes and the world-state materializer
    topics:
      - name: platform.health.degraded
        description: A service health probe transitioned from healthy to degraded or failing
        payload_schema: schemas/events/health_degraded.json
        delivery: at_least_once
        retention: 30d
      - name: platform.health.recovered
        description: A service health probe transitioned back to healthy
        payload_schema: schemas/events/health_recovered.json
        delivery: at_least_once
        retention: 30d

  drift:
    description: Events produced by the drift detector and observation loop
    topics:
      - name: platform.drift.detected
        description: A drift check found divergence between desired and actual state
        payload_schema: schemas/events/drift_detected.json
        delivery: at_least_once
        retention: 30d
      - name: platform.drift.resolved
        description: A drift check that previously fired now shows no divergence
        payload_schema: schemas/events/drift_resolved.json
        delivery: at_least_once
        retention: 30d

  findings:
    description: Events produced by the observation loop (ADR 0071)
    topics:
      - name: platform.findings.observation
        description: A structured finding from an observation loop check
        payload_schema: schemas/events/finding_observation.json
        delivery: at_least_once
        retention: 14d

  incident:
    description: Events produced by the triage engine and incident lifecycle
    topics:
      - name: platform.incident.opened
        description: A triage report was generated for a firing alert
        payload_schema: schemas/events/incident_opened.json
        delivery: at_least_once
        retention: 90d
      - name: platform.incident.resolved
        description: An incident was marked resolved with root cause recorded
        payload_schema: schemas/events/incident_resolved.json
        delivery: at_least_once
        retention: 90d
      - name: platform.incident.escalated
        description: An incident was escalated (auto-check failed or operator requested)
        payload_schema: schemas/events/incident_escalated.json
        delivery: at_least_once
        retention: 90d

  deployment:
    description: Events produced when services are deployed or rolled back
    topics:
      - name: platform.deployment.completed
        description: A service was successfully deployed to a new version
        payload_schema: schemas/events/deployment_completed.json
        delivery: at_least_once
        retention: 90d
      - name: platform.deployment.rolled_back
        description: A service was rolled back to a previous version
        payload_schema: schemas/events/deployment_rolled_back.json
        delivery: at_least_once
        retention: 90d

  agent:
    description: Events produced by agents to coordinate with each other (ADR 0131)
    topics:
      - name: platform.agent.handoff
        description: One agent delegated a task to another agent
        payload_schema: schemas/events/agent_handoff.json
        delivery: exactly_once
        retention: 7d
      - name: platform.agent.state_checkpoint
        description: An agent wrote a state checkpoint (ADR 0130)
        payload_schema: schemas/events/agent_state_checkpoint.json
        delivery: at_least_once
        retention: 7d
```

### Common payload envelope

All events share a top-level envelope regardless of domain:

```json
{
  "event_id":    "uuid",
  "topic":       "platform.execution.completed",
  "schema_ver":  "1.0",
  "ts":          "2026-03-24T14:32:01Z",
  "actor_id":    "agent/triage-loop",
  "context_id":  "uuid",          // SessionContext that produced this event (ADR 0123)
  "payload":     { ... }           // Domain-specific content per schema
}
```

The `context_id` field (from ADR 0123) links the event to the session snapshot that was active when it was produced. This enables complete audit reconstruction: given any event, you can retrieve the exact platform state the actor was operating from.

### JetStream stream configuration

```yaml
# config/nats-streams.yaml

streams:
  - name: PLATFORM_EVENTS
    subjects: ["platform.>"]
    retention: limits
    max_age: 90d
    storage: file
    replicas: 1
    discard: old
    duplicate_window: 2m   # For exactly_once deduplication on agent.handoff
```

All platform domains publish to the single `PLATFORM_EVENTS` stream. Consumers filter by subject.

### Enforcement

A pre-push git hook validates that any new NATS `publish()` call in the codebase uses only a topic declared in `config/event-taxonomy.yaml`. The validation script (`scripts/validate_nats_topics.py`) fails if an undeclared topic is detected, preventing silent topic proliferation.

### Consumer example

```python
# Any component that wants to react to deployments completing:
from platform.events.consumer import EventConsumer

consumer = EventConsumer(subjects=["platform.deployment.completed"])
for event in consumer.stream():
    service = event["payload"]["service_id"]
    new_version = event["payload"]["new_version"]
    # ... react to deployment
```

### Ledger mirroring

Every event published to NATS is also written to the mutation ledger (ADR 0115) via a dedicated Windmill workflow `nats-to-ledger-mirror`. This ensures the ledger remains the complete, queryable audit trail even for consumers that only care about a subset of NATS events.

## Consequences

**Positive**

- All platform event producers and consumers share a single, versioned contract. Payload schema changes require a taxonomy version bump, making breaking changes visible.
- Agents and workflows can react to platform events in real time (deployment complete, health recovered, budget exceeded) without polling the ledger or Mattermost.
- The `context_id` envelope field closes the audit loop between events and the session snapshot (ADR 0123) that produced them.
- The single `PLATFORM_EVENTS` stream with subject filtering is operationally simple: one stream to monitor, one stream to replay.

**Negative / Trade-offs**

- Centralising the taxonomy in `config/event-taxonomy.yaml` means that adding a new event type requires a config change and a pre-push hook pass. This is intentional friction that prevents ad hoc proliferation, but it will occasionally feel bureaucratic for small, exploratory changes.
- The ledger mirror workflow introduces up to a few seconds of lag between a NATS event being published and it appearing in the ledger. Real-time event consumers should read from NATS; retrospective analysis should read from the ledger.
- Exactly-once delivery (used only for `platform.agent.handoff`) requires NATS JetStream with a `duplicate_window`. This is operationally more complex than at-least-once and must be tested carefully for the agent coordination use case.

## Boundaries

- This ADR defines topics and payload envelopes for events that cross component boundaries. Internal Windmill-to-Windmill calls do not need to go through NATS and are not subject to this taxonomy.
- The taxonomy does not define the full JSON schema for each event payload; those schemas live in `schemas/events/` and are referenced by the taxonomy file.
- This ADR does not govern Grafana alert webhook payloads (ADR 0097); those use an established format. The alerting router translates them into `platform.health.degraded` events before publishing to NATS.

## Related ADRs

- ADR 0044: Windmill (workflow execution produces execution.* events)
- ADR 0045: Control-plane communication lanes (existing NATS usage)
- ADR 0057: Mattermost ChatOps (receives bridged events for operator notification)
- ADR 0058: NATS JetStream (underlying transport)
- ADR 0071: Agent observation loop (publishes platform.findings.observation)
- ADR 0091: Continuous drift detection (publishes platform.drift.* events)
- ADR 0097: Alerting routing (translates Grafana alerts into platform.health.degraded)
- ADR 0112: Deterministic goal compiler (publishes platform.intent.*)
- ADR 0114: Rule-based incident triage engine (publishes platform.incident.*)
- ADR 0115: Event-sourced mutation ledger (receives mirrored copies of all events)
- ADR 0119: Budgeted workflow scheduler (publishes platform.execution.*)
- ADR 0123: Agent session bootstrap (context_id envelope field)
- ADR 0131: Multi-agent handoff protocol (consumes platform.agent.handoff)
