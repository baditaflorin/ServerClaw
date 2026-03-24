# Workstream ADR 0130: Agent State Persistence Across Workflow Boundaries

- ADR: [ADR 0130](../adr/0130-agent-state-persistence-across-workflow-boundaries.md)
- Title: Persist in-progress agent state across workflow boundaries with integrity validation after handoff
- Status: merged
- Implemented In Repo Version: 0.122.0
- Implemented On: 2026-03-24
- Branch: `codex/adr-0130-agent-state`
- Worktree: `.worktrees/adr-0130-agent-state`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0098-postgres-ha`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `platform/agent/`, `migrations/`, `scripts/lv3_cli.py`, `docs/runbooks/`

## Scope

- add the `agent.state` Postgres schema with TTL and namespace guardrails
- add `platform.agent.AgentStateClient` for scratch state writes, reads, deletes, checkpoints, and handoff digest verification
- add `lv3 agent state show|delete|verify` for operator inspection and integrity checks
- add focused tests for persistence, TTL filtering, checkpoint publication, and integrity verification
- document the operational usage and verification path in a runbook

## Non-Goals

- live-applying the schema to the platform from this repository change
- defining the separate multi-agent handoff protocol itself
- turning the state store into a permanent case or audit database

## Expected Repo Surfaces

- `migrations/0015_agent_state_schema.sql`
- `platform/agent/__init__.py`
- `platform/agent/state.py`
- `scripts/lv3_cli.py`
- `tests/test_agent_state_client.py`
- `tests/test_lv3_cli.py`
- `docs/runbooks/agent-state-store.md`
- `docs/adr/0130-agent-state-persistence-across-workflow-boundaries.md`
- `docs/workstreams/adr-0130-agent-state-persistence.md`

## Expected Live Surfaces

- the control-plane Postgres instance can host the `agent.state` schema after the migration is applied from `main`
- workflow senders can checkpoint a task snapshot and hand the resulting digest to a downstream workflow
- recipients can verify the active task state against that digest before resuming work

## Verification

- `python3 -m py_compile platform/agent/state.py scripts/lv3_cli.py`
- `uv run --with pytest python -m pytest tests/test_agent_state_client.py tests/test_lv3_cli.py -q`

## Merge Criteria

- the repo has a durable scratch-state client with TTL, size, and active-key limits
- the CLI can inspect, delete, and verify task state without ad hoc SQL
- a handoff digest can be emitted on checkpoint and validated by a fresh client instance after the handoff
