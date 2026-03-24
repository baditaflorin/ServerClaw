# Service Uptime Contracts

## Purpose

This runbook keeps the service uptime contract aligned across:

- `config/health-probe-catalog.json`
- `config/uptime-kuma/monitors.json`
- `config/service-capability-catalog.json`
- the world-state `service_health` surface
- the platform API `GET /v1/platform/health`

## Source Of Truth

The canonical uptime source is `config/health-probe-catalog.json`.

`config/uptime-kuma/monitors.json` is a generated deployment artifact derived from that catalog.

`config/service-capability-catalog.json` remains the service registry and binds operator-facing services to their `uptime_monitor_name`.

## Commands

Regenerate the Uptime Kuma monitor artifact:

```bash
python3 scripts/uptime_contract.py --write
```

Verify the generated monitor artifact is current:

```bash
python3 scripts/uptime_contract.py --check
```

Check the full data-model contract:

```bash
uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate
```

Inspect internal platform health:

```bash
curl -H "Authorization: Bearer <token>" https://api.lv3.org/v1/platform/health
curl -H "Authorization: Bearer <token>" https://api.lv3.org/v1/platform/health/windmill
```

## Update Flow

When a service health surface changes:

1. Update `config/health-probe-catalog.json`.
2. Update `config/service-capability-catalog.json` if the monitor binding or service metadata changed.
3. Regenerate `config/uptime-kuma/monitors.json`.
4. Run the targeted uptime and API tests.
5. Run repository data-model validation.

## Notes

- The world-state collector prefers readiness probes, then liveness probes, then catalog URL fallback when a probe cannot be executed from the worker.
- `command` and `systemd` contracts remain valid convergence checks even when the world-state path cannot execute them directly.
- Internal platform health is no longer limited to the smaller set of services exposed through the API gateway proxy catalog.
