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
- `platform.backup.*`
- `platform.world_state.refreshed`
- `platform.mutation.recorded`

## Validation

Run the dedicated topic validator:

```bash
uv run --with pyyaml python scripts/validate_nats_topics.py --validate
```

Run the full repo gate:

```bash
make validate
```

Check the live JetStream stream state against the committed stream registry:

```bash
make check-nats-streams
```

Apply the committed stream registry to the live NATS runtime through the controller tunnel:

```bash
make apply-nats-streams
```

## Adding A New Topic

1. Add the topic to `config/event-taxonomy.yaml`.
2. If the topic is active now, make sure `config/control-plane-lanes.json` routes it through the event lane.
3. Add or update the matching `config/api-publication.json` classification.
4. Update the publisher to emit the canonical subject and shared envelope.
5. Add or update tests for the producer and, if needed, the validator.
6. Run `uv run --with pyyaml python scripts/validate_nats_topics.py --validate`.

## Live Apply

ADR 0124 remains live only when the repo-managed NATS runtime exposes the committed `PLATFORM_EVENTS`, `RAG_DOCUMENT`, and `SECRET_ROTATION` streams.

1. Run `make check-nats-streams` from a rebased `main` worktree.
2. If the stream is missing or drifted, run `make apply-nats-streams`.
3. Re-run `make check-nats-streams` and confirm the script exits cleanly.
4. Record a live-apply receipt under `receipts/live-applies/`.
5. Update `versions/stack.yaml`, the ADR metadata, and the workstream metadata to the new platform version only after the live check passes.

## Current Live Note

The 2026-03-26 ADR 0124 live apply established the `PLATFORM_EVENTS` stream on the live NATS runtime and verified a canonical `platform.findings.observation` publish into that stream.

ADR 0276 now extends that repo-managed stream contract with `RAG_DOCUMENT` for `rag.document.*` and `SECRET_ROTATION` for `secret.rotation.*`, while `platform.mutation.recorded` stays inside `PLATFORM_EVENTS` so the existing `platform.>` retention contract does not need a destructive stream migration.

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
