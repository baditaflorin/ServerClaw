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

ADR 0124 is not fully live until the internal JetStream runtime exposes the committed `PLATFORM_EVENTS` stream.

1. Run `make check-nats-streams` from a rebased `main` worktree.
2. If the stream is missing or drifted, run `make apply-nats-streams`.
3. Re-run `make check-nats-streams` and confirm the script exits cleanly.
4. Record a live-apply receipt under `receipts/live-applies/`.
5. Update `versions/stack.yaml`, the ADR metadata, and the workstream metadata to the new platform version only after the live check passes.

## Current Live Note

The 2026-03-26 ADR 0124 live apply established the `PLATFORM_EVENTS` stream on the live NATS runtime and verified a canonical `platform.findings.observation` publish into that stream.

That apply also exposed one runtime gap outside the repository-managed stream contract: the host-local NATS auth file at `/opt/nats-jetstream/config/nats-server.conf` still had `jetstream-admin` limited to `$JS.API.>` publishes only. Because that auth file is not yet repo-managed in this repository, the live apply required a manual server-side edit to add `platform.>` to the allow-list and a restart of the `lv3-nats-jetstream` container.

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
