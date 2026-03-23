# Maintenance Windows

This runbook documents the ADR 0080 maintenance-window protocol that suppresses expected alert noise during planned live changes.

## Canonical Surfaces

- `scripts/maintenance_window_tool.py`
- `docs/schema/maintenance-window.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/controller-local-secrets.json`
- `config/control-plane-lanes.json`
- `config/api-publication.json`
- `config/windmill/scripts/maintenance-window.py`

## Current First Iteration Boundary

The current implementation covers:

- NATS KV-backed maintenance-window state in the `maintenance-windows` bucket
- governed `make open-maintenance-window` and `make close-maintenance-window` command surfaces
- observation-loop suppression for non-security findings
- internal NATS events on `maintenance.opened`, `maintenance.closed`, and `maintenance.force_closed`
- an agent-tool query surface for active windows

The current implementation does not yet automate Uptime Kuma, Grafana, or GlitchTip maintenance APIs. Those remain follow-on integrations.

## Current Live Platform Gap

The controller now authenticates to the current live NATS runtime with the local `nats_jetstream_admin_password` secret, and bucket creation plus reads are verified. The remaining live blocker is NATS publish authorization: the current principal set still rejects publishes to `$KV.maintenance-windows.>` on the live platform.

## Open A Window

```bash
make open-maintenance-window \
  SERVICE=grafana \
  REASON="planned grafana restart" \
  DURATION_MINUTES=30
```

The command:

- ensures the `maintenance-windows` KV bucket exists
- writes `maintenance/<service-id>` with the ADR 0080 JSON payload
- sets per-message TTL so the key expires at `auto_close_at`
- emits `maintenance.opened` on the internal NATS event plane

## Close A Window

Close one service-scoped window:

```bash
make close-maintenance-window SERVICE=grafana
```

Force-close every active window:

```bash
make close-maintenance-window SERVICE=all FORCE=true
```

The close command deletes the active KV entry and emits either `maintenance.closed` or `maintenance.force_closed`.

## Query Active Windows

List the active windows directly:

```bash
uv run --with pyyaml --with nats-py python scripts/maintenance_window_tool.py list
```

Or use the governed observe tool:

```bash
python scripts/agent_tool_registry.py --call get-maintenance-windows --args-json '{}'
```

## Observation Loop Suppression

`scripts/platform_observation_tool.py` now reads the active maintenance windows before writing findings and before optional Mattermost or GlitchTip routing.

Suppression rules in this iteration:

- `maintenance/all` suppresses every non-security finding
- service-scoped windows suppress non-security findings whose failing details map to the same `service_id`
- `check-certificate-expiry` and `check-secret-ages` are never suppressible
- suppressed findings stay in the local JSON output and NATS publication stream, but they are not sent to Mattermost or GlitchTip

Suppressed findings now carry:

- `severity: suppressed`
- `original_severity`
- `suppressed: true`
- `maintenance_windows`

## Windmill Usage

The shared Windmill wrapper is:

- `config/windmill/scripts/maintenance-window.py`

Example open:

```python
main(action="open", service_id="grafana", reason="deploy", duration_minutes=20)
```

Example close:

```python
main(action="close", service_id="grafana")
```

## Verification

Repository-level verification:

```bash
python3 -m py_compile scripts/maintenance_window_tool.py scripts/platform_observation_tool.py
uvx --from pyyaml python scripts/validate_repository_data_models.py --validate
uvx --from pytest --with pyyaml --with nats-py python -m pytest tests/test_maintenance_window_tool.py tests/test_platform_observation_tool.py tests/test_agent_tool_registry.py -q
```

Live verification:

1. `make open-maintenance-window SERVICE=grafana REASON="test" DURATION_MINUTES=2`
2. `uv run --with pyyaml --with nats-py python scripts/maintenance_window_tool.py list`
3. `uvx --from pyyaml python scripts/platform_observation_tool.py --checks check-service-health`
4. Confirm any grafana-only service-health failure is written as `suppressed` and is not routed to Mattermost.
5. `make close-maintenance-window SERVICE=grafana`

## Test Harness Override

For deterministic local tests or offline inspection, set:

```bash
export LV3_MAINTENANCE_WINDOWS_FILE=/tmp/maintenance-windows.json
```

When this variable is set, the controller script uses the local JSON file instead of the live NATS KV bucket.
