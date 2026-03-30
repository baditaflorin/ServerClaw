# Workstream ws-0276-live-apply: Live Apply ADR 0276 From Latest `origin/main`

- ADR: [ADR 0276](../adr/0276-nats-jetstream-as-the-platform-event-bus.md)
- Title: Recover and repo-manage the private NATS JetStream runtime, then verify the ADR 0276 event-bus contract live
- Status: in_progress
- Implemented In Repo Version: not yet
- Live Applied In Platform Version: not yet
- Implemented On: not yet
- Live Applied On: not yet
- Branch: `codex/ws-0276-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0276-live-apply`
- Owner: codex
- Depends On: `adr-0023-docker-runtime-guest`, `adr-0065-secret-rotation-automation`, `adr-0079-playbook-decomposition-and-shared-execution-model`, `adr-0115-mutation-ledger`, `adr-0124-platform-event-taxonomy`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0276`, `docs/workstreams/ws-0276-live-apply.md`, `docs/runbooks/nats-jetstream-event-bus.md`, `config/nats-streams.yaml`, `playbooks/nats-jetstream.yml`, `roles/nats_jetstream_runtime/`, `scripts/nats_streams.py`, `scripts/secret_rotation.py`, `platform/ledger/writer.py`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- bring the currently stopped `lv3-nats-jetstream` runtime under repo-managed automation
- reconcile ADR 0276 launch subjects with the existing platform event taxonomy without destroying the live `PLATFORM_EVENTS` history
- verify the current mutation-ledger and secret-rotation publishers use the ADR 0276 subjects
- perform the runtime converge and stream reconcile from this isolated worktree, then record exact evidence for merge-to-main

## Non-Goals

- implementing ADR 0274 or ADR 0275 application-level RAG ingestion consumers
- changing protected release files before the final integration step on `main`
- pretending the previous host-local `/opt/nats-jetstream` state was already repo-managed

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0276-live-apply.md`
- `docs/adr/0276-nats-jetstream-as-the-platform-event-bus.md`
- `docs/runbooks/nats-jetstream-event-bus.md`
- `config/nats-streams.yaml`
- `config/event-taxonomy.yaml`
- `config/control-plane-lanes.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/service-capability-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `playbooks/nats-jetstream.yml`
- `playbooks/services/nats-jetstream.yml`
- `roles/nats_jetstream_runtime/`
- `scripts/nats_streams.py`
- `scripts/secret_rotation.py`
- `platform/ledger/writer.py`
- `tests/test_secret_rotation.py`
- `tests/test_service_id_resolver.py`
- `tests/unit/test_event_taxonomy.py`
- `tests/unit/test_ledger_writer.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-runtime-lv3` serves NATS on TCP `4222` and monitoring on loopback `8222`
- JetStream exposes the committed `PLATFORM_EVENTS`, `RAG_DOCUMENT`, and `SECRET_ROTATION` streams
- `platform.mutation.recorded` publishes into `PLATFORM_EVENTS`
- `secret.rotation.completed` publishes into `SECRET_ROTATION`

## Ownership Notes

- this workstream owns the repo-managed recovery of the currently stopped NATS runtime plus the ADR 0276 stream and subject contract
- `platform.mutation.recorded` remains inside `PLATFORM_EVENTS` by design so the live rollout does not destroy the existing `platform.>` stream history
- if the branch-local live apply completes before safe main integration, the handoff must state exactly which release and integrated-truth files still wait for the merge step
