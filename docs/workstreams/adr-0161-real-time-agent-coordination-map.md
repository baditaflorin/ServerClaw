# Workstream ADR 0161: Real-Time Agent Coordination Map

- ADR: [ADR 0161](../adr/0161-real-time-agent-coordination-map.md)
- Title: JetStream-backed live agent session map surfaced through the API gateway, ops portal, static portal, and agent publishers
- Status: live_applied
- Implemented In Repo Version: 0.156.0
- Implemented In Platform Version: 0.130.10
- Implemented On: 2026-03-25
- Branch: `codex/adr-0161-main-integration`
- Worktree: `.worktrees/adr-0161-main`
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

- `https://api.example.com/v1/platform/agents` returns the current coordination snapshot for authenticated readers
- `https://ops.example.com` shows a live agent coordination panel refreshed from the gateway
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

- repository implementation is merged in repo release `0.156.0`
- the first live apply completed on 2026-03-26 in platform version `0.130.10`
- the coordination runtime, gateway route, interactive ops-portal panel, static snapshot panel, runbook, and snapshot helper are all committed on `main`
- focused ADR 0161 test coverage passed on the integrated mainline for the coordination store, gateway route, interactive ops portal, static ops portal, closure-loop publishing, and observation-loop publishing
- the first coordination snapshot receipt is committed as `receipts/agent-coordination/2026-03-25-adr-0161-agent-coordination-snapshot.json`
- the live rollout is recorded in [receipts/live-applies/2026-03-26-adr-0161-real-time-agent-coordination-map-live-apply.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/live-applies/2026-03-26-adr-0161-real-time-agent-coordination-map-live-apply.json)
