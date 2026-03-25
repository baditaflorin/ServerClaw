# Platform Event Taxonomy

ADR 0124 makes `config/event-taxonomy.yaml` the canonical registry for platform NATS topics and their minimum payload contract.

## What Is Canonical

- active platform events live under `platform.*`
- event routing in `config/control-plane-lanes.json` must cover every active topic family
- publishers wrap payloads in the shared event envelope before sending to NATS
- `scripts/validate_nats_topics.py` is the enforcement gate used by `make validate` and the local pre-push hook

## Current Active Topic Families

- `platform.api.request`
- `platform.findings.observation`
- `platform.drift.*`
- `platform.security.*`
- `platform.maintenance.*`
- `platform.backup.restore-verification.*`
- `platform.world_state.refreshed`
- `platform.ledger.event_written`

## Validation

Run the dedicated topic validator:

```bash
uv run --with pyyaml python scripts/validate_nats_topics.py --validate
```

Run the full repo gate:

```bash
make validate
```

## Adding A New Topic

1. Add the topic to `config/event-taxonomy.yaml`.
2. If the topic is active now, make sure `config/control-plane-lanes.json` routes it through the event lane.
3. Add or update the matching `config/api-publication.json` classification.
4. Update the publisher to emit the canonical subject and shared envelope.
5. Add or update tests for the producer and, if needed, the validator.
6. Run `uv run --with pyyaml python scripts/validate_nats_topics.py --validate`.

## Envelope Shape

Each published event is wrapped as:

```json
{
  "event_id": "uuid",
  "topic": "platform.maintenance.opened",
  "schema_ver": "1.0",
  "ts": "2026-03-24T20:00:00Z",
  "actor_id": "service/maintenance-window-tool",
  "payload": {}
}
```

Use `platform/events/taxonomy.py` to build and validate the envelope instead of hand-rolling JSON in each publisher.
