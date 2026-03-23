# Workstream ADR 0092: Unified Platform API Gateway

- ADR: [ADR 0092](../adr/0092-unified-platform-api-gateway.md)
- Title: FastAPI + Caddy gateway aggregating all platform service APIs behind a single authenticated endpoint at api.lv3.org
- Status: ready
- Branch: `codex/adr-0092-platform-api-gateway`
- Worktree: `../proxmox_florin_server-api-gateway`
- Owner: codex
- Depends On: `adr-0021-nginx-edge`, `adr-0045-communication-lanes`, `adr-0047-mtls`, `adr-0056-keycloak`, `adr-0058-nats`, `adr-0066-audit-log`, `adr-0069-agent-tool-registry`
- Conflicts With: none
- Shared Surfaces: `config/`, `playbooks/services/`, Compose stacks on `docker-runtime-lv3`, nginx edge config

## Scope

- write `scripts/api_gateway/main.py` — FastAPI application with JWT validation, service routing, NATS event emission, and native `/v1/platform/*` endpoints
- write `config/api-gateway-catalog.json` — service routing catalog (all existing services)
- write Ansible role `api_gateway_runtime` — deploys the gateway Compose stack
- write `playbooks/services/api-gateway.yml` — service deployment playbook
- add nginx vhost `api.lv3.org` on `nginx-lv3` with mTLS to gateway
- register Keycloak client `api-gateway`
- add health probe for gateway to `config/health-probe-catalog.json`
- add gateway entry to `config/service-capability-catalog.json`
- add `config/subdomain-catalog.json` entry for `api.lv3.org`
- write Grafana dashboard `config/grafana/dashboards/api-gateway.json`
- update `config/agent-tool-registry.json` — all tools now resolve URLs from the gateway catalog

## Non-Goals

- proxying database connections (Postgres, Redis) — these remain direct
- proxying binary/gRPC protocols (step-ca ACME, OpenBao Agent)
- rate limiting or circuit breaking in this iteration

## Expected Repo Surfaces

- `scripts/api_gateway/` (new directory with FastAPI app)
- `roles/api_gateway_runtime/`
- `playbooks/services/api-gateway.yml`
- `config/api-gateway-catalog.json`
- `config/service-capability-catalog.json` (patched)
- `config/health-probe-catalog.json` (patched)
- `config/subdomain-catalog.json` (patched)
- `config/grafana/dashboards/api-gateway.json`
- `inventory/group_vars/docker_runtime.yml` (patched: gateway vars)
- `docs/adr/0092-unified-platform-api-gateway.md`
- `docs/workstreams/adr-0092-platform-api-gateway.md`

## Expected Live Surfaces

- `https://api.lv3.org/v1/health` returns HTTP 200 with `{"status": "healthy"}`
- `https://api.lv3.org/v1/platform/services` returns the full service catalog
- All existing agent tools in `config/agent-tool-registry.json` resolve via `api.lv3.org`

## Verification

- `curl -H "Authorization: Bearer $(lv3 token)" https://api.lv3.org/v1/health` → 200
- `curl -H "Authorization: Bearer $(lv3 token)" https://api.lv3.org/v1/platform/services` → lists all services
- `curl https://api.lv3.org/v1/health` (no token) → 401
- Grafana API Gateway dashboard shows request rate > 0 after running the above

## Merge Criteria

- Gateway deployed and healthy on `docker-runtime-lv3`
- `api.lv3.org` resolves and is TLS-terminated by nginx with OIDC
- All 5 native `/v1/platform/*` endpoints return valid responses
- NATS event `platform.api.request` is published and receivable (verify with `nats sub platform.api.request`)
- Health probe in `config/health-probe-catalog.json` passes

## Notes For The Next Assistant

- The FastAPI app must use `httpx.AsyncClient` with connection pooling for upstream requests; do not create a new client per request
- JWT validation must use the JWKS endpoint, not a static key; Keycloak rotates its signing keys periodically
- The `/v1/platform/topology` endpoint calls the Proxmox API directly; use the existing `lv3_automation@pve` credentials from OpenBao
- The API gateway catalog JSON schema must be validated by `scripts/validate_repository_data_models.py` — add a schema for `api-gateway-catalog.json`
