# Workstream ADR 0131: Multi-Agent Handoff Protocol

- ADR: [ADR 0131](../adr/0131-multi-agent-handoff-protocol.md)
- Title: Add a durable, auditable handoff protocol so agents and operators can transfer task ownership without hidden context
- Status: merged
- Implemented In Repo Version: 0.122.0
- Implemented On: 2026-03-24
- Branch: `codex/adr-0131-handoff-protocol`
- Worktree: `.worktrees/adr-0131`
- Owner: codex
- Depends On: `adr-0090-platform-cli`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `platform/handoff/`, `scripts/lv3_cli.py`, `config/ledger-event-types.yaml`, `migrations/0015_handoff_schema.sql`, `docs/runbooks/`

## Scope

- add the `platform.handoff` package with typed handoff messages, responses, durable transfer records, and fallback handling
- add an in-memory transport so repository verification can exercise retries, refusal, timeout, and load burst handling without a live NATS dependency
- extend `lv3` with `handoff send/list/view/accept/refuse/complete`
- add the `handoff.transfers` schema migration and register the handoff lifecycle events in the ledger event registry
- document the operator workflow and record ADR 0131 as implemented in repo version `0.122.0`

## Non-Goals

- live-applying a NATS subscriber to the platform in the same change
- implementing the broader ADR 0125 or ADR 0130 surfaces beyond what the handoff protocol needs directly
- changing existing triage or runbook executor workflows to emit handoffs automatically

## Expected Repo Surfaces

- `platform/handoff/__init__.py`
- `platform/handoff/core.py`
- `scripts/lv3_cli.py`
- `config/ledger-event-types.yaml`
- `migrations/0015_handoff_schema.sql`
- `tests/unit/test_handoff_protocol.py`
- `tests/test_lv3_cli.py`
- `docs/adr/0131-multi-agent-handoff-protocol.md`
- `docs/runbooks/agent-handoff-protocol.md`
- `docs/workstreams/adr-0131-agent-handoff-protocol.md`

## Expected Live Surfaces

- none yet; this change is a repository implementation and validation surface only

## Verification

- `python3 -m py_compile platform/handoff/core.py scripts/lv3_cli.py`
- `uv run --with pytest python -m pytest tests/unit/test_handoff_protocol.py tests/test_lv3_cli.py -q`
- `uv run --with pyyaml python scripts/generate_status_docs.py --check`

## Merge Criteria

- the repo can create, persist, accept, refuse, and complete handoffs through `platform.handoff`
- fallback handling is explicit for timeout and refusal cases
- a concurrent handoff burst completes without duplicate records or dropped acceptances
- the operator-facing runbook and ADR metadata are current
