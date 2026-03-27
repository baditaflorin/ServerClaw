# Workstream ADR 0167: Graceful Degradation Mode Declarations

- ADR: [ADR 0167](../adr/0167-graceful-degradation-mode-declarations.md)
- Title: declared fallback behaviour for dependency failures, live degraded-state tracking, and API gateway enforcement
- Status: live_applied
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

- repository implementation is complete on `main` in repo release `0.146.1`
- the mainline now carries the declaration schema, gateway degraded-mode runtime, health surfacing, and operator runbooks
- patch release `0.146.1` fixes API gateway repo-root discovery for the packaged container layout so the bundled `platform/` package resolves correctly at runtime
- current-main release `0.164.0` completed the merged replay and recorded the first live platform state in platform version `0.130.15`

## Live Apply Attempt 2026-03-25

- targeted repository validation passed on commit `e73ce5b`
- converging `playbooks/api-gateway.yml` through the public Proxmox jump succeeded through file sync, config render, and image build
- the first live attempt exposed a packaged-path regression in `scripts/api_gateway/main.py`; release `0.146.1` fixes that by discovering the repo root from either the source-tree or packaged layout
- the second live attempt reached `docker compose up`, but Docker failed to publish `8083` because the guest lost the `DOCKER` nat chain during container recreate: `iptables: No chain/target/match by that name`
- after that failure, new SSH sessions to the public Proxmox host at `65.108.75.123:22` began timing out from this controller environment, so the Docker restart/retry step could not be completed in the same turn

## Live Apply 2026-03-26

- replaying `playbooks/api-gateway.yml` from merged `main` succeeded on `docker-runtime-lv3` with `ok=125 changed=25 unreachable=0 failed=0 skipped=24`
- the runtime verification steps passed during converge, including the authenticated platform service catalog probe and the anonymous aggregate-health canonical-error assertion
- the public endpoint `https://api.lv3.org/v1/platform/degradations` returned `{"degradation_count":0,"services":{}}` after the replay
- the authenticated public endpoint `https://api.lv3.org/v1/platform/services` reported `api_gateway.active_degradations: []`
- guest state under `/opt/api-gateway/data/degradation-state.json` showed an empty `services` object and `/opt/api-gateway/data/nats-outbox.jsonl` was absent after recovery
