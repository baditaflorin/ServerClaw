# Workstream ADR 0123: Service Uptime Contracts And Monitor-Backed Health

- ADR: [ADR 0123](../adr/0123-service-uptime-contracts-and-monitor-backed-health.md)
- Title: Make the health-probe catalog the canonical uptime contract for Uptime Kuma, world-state, the platform API, and the interactive ops portal
- Status: merged
- Implemented In Repo Version: 0.121.0
- Implemented On: 2026-03-24
- Branch: `codex/adr-0123-service-uptime-contract`
- Worktree: `.worktrees/adr-0123`
- Owner: codex
- Depends On: `adr-0027-uptime-kuma`, `adr-0064-health-probe-contracts`, `adr-0075-service-capability-catalog`, `adr-0092-platform-api-gateway`, `adr-0093-interactive-ops-portal`, `adr-0113-world-state-materializer`
- Conflicts With: none
- Shared Surfaces: `config/health-probe-catalog.json`, `config/uptime-kuma/monitors.json`, `platform/world_state/`, `scripts/api_gateway/`, `scripts/ops_portal/`, `docs/runbooks/`

## Scope

- add ADR 0123 documenting contract-backed uptime across Uptime Kuma and internal health surfaces
- add `scripts/uptime_contract.py` to generate `config/uptime-kuma/monitors.json` from `config/health-probe-catalog.json`
- make repository validation enforce the generated monitor artifact order and fields
- make `platform/world_state/workers.py` use the health-probe contract for HTTP and TCP service checks before falling back to catalog URLs
- make the platform API gateway expose service-catalog-backed platform health plus a per-service health endpoint
- fix the interactive ops portal health normalization to accept `service_id` payloads from the real gateway
- update runbooks so the Uptime Kuma monitor file is treated as generated, not hand-maintained
- add focused tests for contract generation, world-state probing, API health endpoints, and portal normalization

## Non-Goals

- live-applying the new uptime contract to the platform from this change
- replacing command or systemd readiness probes with network probes when those contracts are still correct
- redesigning the public status page or the Uptime Kuma UI itself

## Expected Repo Surfaces

- `scripts/uptime_contract.py`
- `config/uptime-kuma/monitors.json`
- `platform/world_state/workers.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/app.py`
- `tests/test_uptime_contract.py`
- `tests/test_world_state_workers.py`
- `tests/test_api_gateway.py`
- `tests/test_interactive_ops_portal.py`
- `docs/runbooks/service-uptime-contracts.md`
- `docs/adr/0123-service-uptime-contracts-and-monitor-backed-health.md`
- `docs/workstreams/adr-0123-service-uptime-contracts.md`

## Expected Live Surfaces

- `make uptime-kuma-manage ACTION=ensure-monitors` applies a generated monitor set, not a hand-edited duplicate
- `GET /v1/platform/health` reports active services from the service catalog with world-state or live-probe status
- `GET /v1/platform/health/{service_id}` returns a single active service health record
- the interactive ops portal shows live platform health for most managed services once this is deployed from `main`

## Verification

- `python3 -m py_compile scripts/uptime_contract.py scripts/api_gateway/main.py scripts/ops_portal/app.py platform/world_state/workers.py scripts/validate_repository_data_models.py`
- `python3 scripts/uptime_contract.py --check`
- `uv run --with pytest python -m pytest tests/test_uptime_contract.py tests/test_world_state_workers.py -q`
- `uv run --with pytest --with fastapi --with httpx --with cryptography python -m pytest tests/test_api_gateway.py -q`
- `uv run --with pytest --with fastapi --with httpx --with jinja2 --with itsdangerous --with python-multipart --with pyyaml --with jsonschema python -m pytest tests/test_interactive_ops_portal.py tests/test_validate_service_catalog.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- `config/uptime-kuma/monitors.json` is generated from the health-probe catalog and validated as such
- the world-state service-health collector prefers contract probes over guessed service URLs
- the platform API gateway returns service-catalog-backed platform health and a per-service health endpoint
- the interactive ops portal correctly renders health payloads from the real gateway schema
