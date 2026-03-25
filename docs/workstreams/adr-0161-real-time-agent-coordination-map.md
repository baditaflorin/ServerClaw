# Workstream ADR 0161: Real-Time Agent Coordination Map

- ADR: [ADR 0161](../adr/0161-real-time-agent-coordination-map.md)
- Title: JetStream-backed live agent session map surfaced through the API gateway, ops portal, static portal, and agent publishers
- Status: in_progress
- Implemented In Repo Version: 0.144.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Branch: `codex/adr-0161-real-time-agent-coordination-map`
- Worktree: `.worktrees/adr-0161-live-apply`
- Owner: codex
- Depends On: `adr-0058-nats`, `adr-0092-platform-api-gateway`, `adr-0093-interactive-ops-portal`, `adr-0114-incident-triage`, `adr-0126-observation-loop`
- Conflicts With: none
- Shared Surfaces: `platform/agent/`, `platform/closure_loop/`, `scripts/api_gateway/main.py`, `scripts/ops_portal/`, `scripts/generate_ops_portal.py`, `config/windmill/scripts/platform-observation-loop.py`, `receipts/agent-coordination/`

## Scope

- add a repo-managed coordination store with JetStream KV support and file-backed fallback for offline tests
- publish coordination entries from active agent flows, starting with the observation loop and closure loop
- expose the live coordination snapshot through the platform API gateway
- render the live coordination map in the interactive ops portal and the latest recorded snapshot in the static ops portal
- add an operator snapshot tool that writes coordination receipts under `receipts/agent-coordination/`
- document the runtime, verification, and troubleshooting path in a dedicated runbook

## Non-Goals

- replacing the lock registry or intent queue with the coordination map
- introducing a historical replay system for all agent activity
- claiming all future agent workflows already publish coordination entries on day one

## Expected Repo Surfaces

- `platform/agent/coordination.py`
- `platform/closure_loop/engine.py`
- `config/windmill/scripts/platform-observation-loop.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/`
- `scripts/generate_ops_portal.py`
- `scripts/agent_coordination_snapshot.py`
- `docs/runbooks/agent-coordination-map.md`
- `docs/adr/0161-real-time-agent-coordination-map.md`
- `docs/workstreams/adr-0161-real-time-agent-coordination-map.md`
- `tests/test_agent_coordination.py`
- `tests/test_api_gateway.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal.py`

## Expected Live Surfaces

- `https://api.lv3.org/v1/platform/agents` returns the current coordination snapshot for authenticated readers
- `https://ops.lv3.org` shows a live agent coordination panel refreshed from the gateway
- the static generated ops portal shows the latest recorded coordination snapshot receipt when one is committed
- active observation-loop and closure-loop sessions publish into the shared coordination bucket

## Verification

- `uv run --with pytest --with-requirements requirements/api-gateway.txt python -m pytest -q tests/test_agent_coordination.py tests/test_api_gateway.py`
- `uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_interactive_ops_portal.py tests/test_ops_portal.py`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/unit/test_closure_loop.py tests/test_closure_loop_windmill.py`
- `uv run --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --check`
- `python3 scripts/agent_coordination_snapshot.py --repo-root .`

## Merge Criteria

- active agent sessions appear in the coordination snapshot with phase, target, and heartbeat data
- the gateway endpoint is authenticated and returns a stable summary plus entries payload
- the interactive ops portal renders the coordination panel without breaking the existing deployment, drift, or runbook surfaces
- the static portal can render a recorded coordination snapshot receipt without requiring live network access

## Outcome

- pending live apply, receipt capture, version bump, and final status update
