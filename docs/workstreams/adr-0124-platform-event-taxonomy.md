# Workstream ADR 0124: Platform Event Taxonomy And Canonical NATS Topics

- ADR: [ADR 0124](../adr/0124-platform-event-taxonomy-and-canonical-nats-topics.md)
- Title: Canonicalize the platform event plane around one NATS taxonomy and validated routing contract
- Status: merged
- Implemented In Repo Version: 0.127.0
- Implemented On: 2026-03-24
- Branch: `codex/adr-0124-platform-event-taxonomy`
- Worktree: `.worktrees/adr-0124`
- Owner: codex
- Depends On: `adr-0058-nats-event-bus`, `adr-0071-agent-observation-loop`, `adr-0080-maintenance-windows`, `adr-0092-platform-api-gateway`, `adr-0099-backup-restore-verification`, `adr-0102-security-posture-reporting`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `config/event-taxonomy.yaml`, `config/nats-streams.yaml`, `config/control-plane-lanes.json`, `config/api-publication.json`, `platform/events/`, `scripts/validate_nats_topics.py`, `docs/runbooks/`

## Scope

- add ADR 0124 to the repo as the canonical event-taxonomy decision record
- define the active and reserved `platform.*` NATS topics in `config/event-taxonomy.yaml`
- add a shared event-envelope helper used by current publishers
- move maintenance-window, world-state, and mutation-ledger fan-out onto canonical `platform.*` topics
- collapse observation-loop publication onto `platform.findings.observation`
- validate code-published topics and event-lane routing against the canonical taxonomy
- update the lane catalog, API publication catalog, and runbooks to match the new routing contract

## Non-Goals

- live-applying any NATS permission or consumer changes on the platform in this workstream
- implementing the reserved intent, execution, health, incident, deployment, or agent topics beyond documenting their contract
- replacing the mutation ledger as the durable audit trail

## Expected Repo Surfaces

- `config/event-taxonomy.yaml`
- `config/nats-streams.yaml`
- `platform/events/taxonomy.py`
- `scripts/validate_nats_topics.py`
- updated publisher call sites under `scripts/` and `platform/`
- updated `config/control-plane-lanes.json`
- updated `config/api-publication.json`
- updated runbooks and related ADR/workstream docs
- `docs/adr/0124-platform-event-taxonomy-and-canonical-nats-topics.md`
- `docs/workstreams/adr-0124-platform-event-taxonomy.md`

## Expected Live Surfaces

- a single `PLATFORM_EVENTS` stream bound to `platform.>` on the internal NATS runtime
- current publishers emitting canonical `platform.*` subjects with the shared envelope
- subscribers validating against `platform.findings.observation`, `platform.maintenance.*`, `platform.world_state.refreshed`, and `platform.ledger.event_written` instead of legacy ad hoc subjects

## Verification

- `python3 -m py_compile scripts/validate_nats_topics.py scripts/drift_lib.py scripts/platform_observation_tool.py scripts/maintenance_window_tool.py scripts/api_gateway/main.py platform/world_state/workers.py platform/world_state/materializer.py platform/ledger/writer.py platform/events/taxonomy.py`
- `uv run --with pyyaml python scripts/validate_nats_topics.py --validate`
- `uv run --with pytest python -m pytest tests/unit/test_event_taxonomy.py tests/unit/test_ledger_writer.py tests/test_platform_observation_tool.py tests/test_drift_detector.py tests/test_security_posture_report.py tests/test_world_state_workers.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- every active platform NATS topic is declared in `config/event-taxonomy.yaml`
- the event lane catalog routes every active topic family declared by the taxonomy
- the observation loop, maintenance-window tool, world-state materializer, API gateway, backup verification publisher, and ledger fan-out all publish canonical `platform.*` subjects
- `make validate` fails when a code publisher or routed event surface drifts from the taxonomy
