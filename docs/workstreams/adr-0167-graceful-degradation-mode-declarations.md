# Workstream ADR 0167: Graceful Degradation Mode Declarations

- ADR: [ADR 0167](../adr/0167-graceful-degradation-mode-declarations.md)
- Title: declared fallback behaviour for dependency failures, live degraded-state tracking, and API gateway enforcement
- Status: ready_for_merge
- Branch: `codex/adr-0167-graceful-degradation-mode-declarations`
- Worktree: `.worktrees/adr-0167-graceful-degradation`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0092-platform-api-gateway`, `adr-0128-health-composite-index`
- Conflicts With: none
- Shared Surfaces: `config/service-capability-catalog.json`, `docs/schema/service-capability-catalog.schema.json`, `scripts/service_catalog.py`, `scripts/api_gateway/main.py`, `platform/health/composite.py`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`, `docs/runbooks/`

## Scope

- extend the service capability catalog so services can declare dependency-specific degradation modes
- validate and render those declarations through the existing operator-facing catalog tooling
- add a repo-managed degraded-state store so live services can record active degradations without ad hoc shell notes
- teach the API gateway to degrade cleanly when Keycloak JWKS refreshes fail and when NATS request-event publication fails
- surface active degraded modes through the platform API health and service endpoints
- document the operator inspection and verification workflow

## Non-Goals

- implementing a shared distributed circuit-breaker runtime for every platform service in this workstream
- replacing service-specific reconnect logic that already exists in upstream applications
- inventing an unaudited manual fallback path outside repo-managed automation

## Expected Repo Surfaces

- `config/service-capability-catalog.json`
- `docs/schema/service-capability-catalog.schema.json`
- `scripts/service_catalog.py`
- `scripts/api_gateway/main.py`
- `platform/degradation/state.py`
- `platform/health/composite.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/templates/api-gateway.env.j2`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/templates/docker-compose.yml.j2`
- `docs/runbooks/graceful-degradation-modes.md`
- `docs/runbooks/configure-api-gateway.md`
- `docs/workstreams/adr-0167-graceful-degradation-mode-declarations.md`
- `tests/test_api_gateway.py`
- `tests/test_health_composite.py`
- `tests/test_validate_service_catalog.py`

## Expected Live Surfaces

- the API gateway keeps serving authenticated requests from cached JWKS during a bounded Keycloak outage
- the API gateway returns an explicit `503` plus `Retry-After` once that cache expires instead of falling back to an ambiguous auth failure
- request events buffer in a repo-managed local outbox when NATS publication fails and flush on recovery
- operators can inspect live degraded state from both the gateway runtime data directory and `/v1/platform/degradations`

## Verification

- `python3 -m py_compile scripts/service_catalog.py scripts/api_gateway/main.py platform/health/composite.py platform/degradation/state.py`
- `uv run --with pytest --with jsonschema --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 pytest tests/test_validate_service_catalog.py tests/test_health_composite.py tests/test_api_gateway.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/service_catalog.py --validate`
- `make syntax-check-api-gateway`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- degradation declarations are schema-validated and operator-visible through the catalog tooling
- active degraded state is recorded in repo-managed files instead of hidden in logs
- the gateway honours the declared Keycloak and NATS degraded behaviour under automated tests
- the health and service endpoints surface active degraded modes clearly enough for operators to act on them

## Outcome

- branch-local implementation is complete and verified
- integration-only release, ADR status, and live-state updates should be applied on `main`
