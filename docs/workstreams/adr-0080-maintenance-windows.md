# Workstream ADR 0080: Maintenance Window And Change Suppression Protocol

- ADR: [ADR 0080](../adr/0080-maintenance-window-and-change-suppression-protocol.md)
- Title: NATS KV-backed maintenance windows with multi-surface suppression for planned outages
- Status: merged
- Branch: `codex/adr-0080-maintenance-windows`
- Worktree: `../proxmox_florin_server-maintenance-windows`
- Owner: codex
- Depends On: `adr-0058-nats-event-bus`, `adr-0057-mattermost-chatops`, `adr-0044-windmill`, `adr-0071-agent-observation-loop`, `adr-0027-uptime-kuma`
- Conflicts With: none
- Shared Surfaces: NATS KV store (`maintenance-windows` bucket), `scripts/maintenance_window_tool.py`, `scripts/platform_observation_tool.py`, `config/command-catalog.json`, `config/control-plane-lanes.json`, `Makefile`

## Scope

- create NATS KV bucket `maintenance-windows` on the NATS JetStream instance
- define maintenance window JSON schema in `docs/schema/maintenance-window.json`
- add `open-maintenance-window` and `close-maintenance-window` commands to `config/command-catalog.json`
- add `make open-maintenance-window SERVICE=... REASON=... DURATION_MINUTES=...` target
- add `make close-maintenance-window SERVICE=... [FORCE=true]` target
- update the observation loop (ADR 0071) to check `maintenance/<service-id>` and `maintenance/all` before emitting Mattermost notifications
- write a Windmill helper function `maintenance_window_open(service_id, duration_min)` for use in the deploy-and-promote workflow (ADR 0073)
- configure NATS KV TTL to auto-delete keys at `auto_close_at` timestamp
- document the protocol in `docs/runbooks/maintenance-windows.md`

## Non-Goals

- Uptime Kuma API suppression in the first iteration (manual workaround: operator pauses the monitor; API integration is a follow-on)
- multi-timezone scheduled maintenance windows (windows are specified in UTC only)
- widening the current live NATS writer permissions; the current platform still needs a dedicated maintenance-window writer principal or equivalent permission update

## Expected Repo Surfaces

- `docs/schema/maintenance-window.json`
- updated `config/command-catalog.json`
- updated `Makefile` (`open-maintenance-window`, `close-maintenance-window` targets)
- Windmill helper function definition
- `docs/runbooks/maintenance-windows.md`
- `docs/adr/0080-maintenance-window-and-change-suppression-protocol.md`
- `docs/workstreams/adr-0080-maintenance-windows.md`
- `workstreams.yaml`

## Expected Live Surfaces

- NATS KV bucket `maintenance-windows` created on NATS JetStream
- `make open-maintenance-window SERVICE=grafana REASON="test" DURATION_MINUTES=5` writes a key and the observation loop suppresses Mattermost notifications for that service for 5 minutes
- `make close-maintenance-window SERVICE=grafana` deletes the key and notifications resume

## Current Live Blocker

- the controller can authenticate to the current live NATS runtime with the local `jetstream-admin` password, and bucket creation plus reads now work
- the current live NATS principal set still rejects publishes to `$KV.maintenance-windows.>` with `permissions violation for publish to "$kv.maintenance-windows.maintenance/<service>"`
- this workstream is therefore merged in repository automation but not yet live-applied on the platform

## Verification

- `python3 -m py_compile scripts/maintenance_window_tool.py scripts/platform_observation_tool.py scripts/agent_tool_registry.py config/windmill/scripts/maintenance-window.py`
- `uvx --from pytest --with pyyaml --with nats-py python -m pytest tests/test_maintenance_window_tool.py tests/test_platform_observation_tool.py tests/test_agent_tool_registry.py -q`
- `uvx --from pyyaml python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml --with nats-py python scripts/maintenance_window_tool.py ensure-bucket`
- `uv run --with pyyaml --with nats-py python scripts/maintenance_window_tool.py list`

## Merge Criteria

- observation loop correctly suppresses non-security findings during an open window
- security findings are not suppressible (tested with a simulated certificate expiry finding)
- the repository exposes governed open, close, list, Windmill, and agent-tool surfaces for maintenance windows
- `make open-maintenance-window` and `make close-maintenance-window` are documented

## Notes For The Next Assistant

- NATS KV TTL is set in seconds at key creation time using the JetStream KV Put API `opts.TTL` field; do not rely on a scheduled Windmill job for auto-close — use the TTL natively
- the Windmill helper function should be a shared script in the `lv3` workspace, not embedded in the deploy workflow — other workflows (e.g. secret rotation) will also need to open windows
- the remaining platform gap is NATS publish rights for `$KV.maintenance-windows.>` and the chosen maintenance event subject prefix, not missing repository automation
