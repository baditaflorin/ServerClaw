# ADR 0124: Platform Event Taxonomy And Canonical NATS Topics

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.127.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

NATS JetStream is already the internal event bus for the platform, but subject naming and payload structure had drifted by producer:

- the observation loop published one subject per check
- maintenance windows used a separate `maintenance.*` namespace outside the platform event plane
- world-state refresh and mutation-ledger fan-out used standalone subjects outside the canonical platform namespace
- new producers had no single registry to check before adding another topic

That made message routing brittle. Consumers had to know producer-specific topic conventions, and the event lane catalog could not validate whether the documented subjects still matched the code that actually published them.

## Decision

We will treat `config/event-taxonomy.yaml` as the canonical registry for platform NATS topics and the minimum payload contract for each topic. All active platform event subjects now live under the `platform.*` namespace, and publishers wrap payloads in a shared event envelope before sending them to NATS.

The registry distinguishes:

- `active` topics already emitted by repository code
- `reserved` topics that are part of the forward contract for upcoming ADRs in the same control-plane series

The current active canonical topics are:

- `platform.api.request`
- `platform.findings.observation`
- `platform.drift.warn`
- `platform.drift.critical`
- `platform.drift.unreachable`
- `platform.security.report`
- `platform.security.critical-finding`
- `platform.maintenance.opened`
- `platform.maintenance.closed`
- `platform.maintenance.force_closed`
- `platform.backup.restore-verification.completed`
- `platform.backup.restore-verification.failed`
- `platform.world_state.refreshed`
- `platform.ledger.event_written`

Each published event uses the shared envelope:

```json
{
  "event_id": "uuid",
  "topic": "platform.findings.observation",
  "schema_ver": "1.0",
  "ts": "2026-03-24T20:00:00Z",
  "actor_id": "agent/observation-loop",
  "payload": {
    "check": "check-vm-state",
    "severity": "ok"
  }
}
```

The platform stream contract is recorded in `config/nats-streams.yaml` with a single `PLATFORM_EVENTS` stream bound to `platform.>`.

## Implementation

This ADR is implemented in repository automation by:

- adding `config/event-taxonomy.yaml` as the canonical topic registry
- adding `config/nats-streams.yaml` for the canonical JetStream stream definition
- adding `platform/events/taxonomy.py` to validate payloads and build the shared event envelope
- moving remaining off-taxonomy publishers to `platform.maintenance.*`, `platform.world_state.refreshed`, and `platform.ledger.event_written`
- canonicalizing observation-loop publication onto `platform.findings.observation`
- validating both code-published topics and event-lane routing with `scripts/validate_nats_topics.py`
- wiring the new validation into `make validate` and the local pre-push hook
- updating `config/control-plane-lanes.json` and `config/api-publication.json` so the documented event lane matches the active taxonomy

## Consequences

### Positive

- New publishers must register a subject before they can pass validation.
- The event lane catalog and the code now validate against the same source of truth.
- Subscribers can rely on stable, canonical topics instead of producer-specific naming conventions.
- The remaining reserved topics give the ADR 0125+ control-plane work a forward contract without requiring ad hoc topic invention later.

### Negative

- Adding even a small exploratory event now requires updating the registry and the validator.
- Existing docs and downstream consumers must follow the canonicalized subject moves from `maintenance.*`, `world_state.refreshed`, `ledger.event_written`, and per-check finding subjects.

## Follow-On Notes

- The shared envelope already allows an optional `context_id`, but most current publishers do not populate it yet.
- Reserved topics stay documented here so later ADRs can activate them by adding producers rather than redefining the taxonomy.
