# Workstream ADR 0092: Unified Platform API Gateway

- ADR: [ADR 0092](../adr/0092-unified-platform-api-gateway.md)
- Title: FastAPI gateway aggregating all platform service APIs behind a single authenticated endpoint at api.example.com
- Status: live_applied
- Branch: `codex/integration-0092-live`
- Worktree: `.worktrees/integration-0092`
- Owner: codex
- Depends On: `adr-0021-nginx-edge`, `adr-0045-communication-lanes`, `adr-0047-mtls`, `adr-0056-keycloak`, `adr-0058-nats`, `adr-0066-audit-log`, `adr-0069-agent-tool-registry`
- Conflicts With: none
- Shared Surfaces: `config/`, `playbooks/services/`, Compose stacks on `docker-runtime`, nginx edge config

## Scope

- write `scripts/api_gateway/main.py` — FastAPI application with JWT validation, service routing, NATS event emission, and native `/v1/platform/*` endpoints
- write `config/api-gateway-catalog.json` — service routing catalog (all existing services)
- write Ansible role `api_gateway_runtime` — deploys the gateway Compose stack
- write `playbooks/services/api-gateway.yml` — service deployment playbook
- add nginx vhost `api.example.com` on `nginx-edge` with mTLS to gateway
- register Keycloak client `api-gateway`
- add health probe for gateway to `config/health-probe-catalog.json`
- add gateway entry to `config/service-capability-catalog.json`
- add `config/subdomain-catalog.json` entry for `api.example.com`
- write Grafana dashboard `config/grafana/dashboards/api-gateway.json`
- update `config/agent-tool-registry.json` — all tools now resolve URLs from the gateway catalog

## Non-Goals

- proxying database connections (Postgres, Redis) — these remain direct
- proxying binary/gRPC protocols (step-ca ACME, OpenBao Agent)
- rate limiting or circuit breaking in this iteration

## Expected Repo Surfaces

- `scripts/api_gateway/` (new directory with FastAPI app)
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`
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

- `https://api.example.com/healthz` returns HTTP 200 with `{"status":"ok"}`
- `https://api.example.com/v1/health` returns `401` without a bearer token
- `https://api.example.com/v1/platform/services` returns the full service catalog with a valid Keycloak bearer token
- All existing agent tools in `config/agent-tool-registry.json` resolve via `api.example.com`

## Verification

- `ansible-playbook -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/api-gateway.yml` → passes and verifies a real bearer token against `/v1/platform/services`
- `curl https://api.example.com/healthz` → `200 {"status":"ok"}`
- `curl https://api.example.com/v1/health` (no token) → `401`
- `curl -H "Authorization: Bearer <realm token>" https://api.example.com/v1/platform/services` → `200` with `24` services

## Merge Criteria

- Gateway deployed and healthy on `docker-runtime`
- `api.example.com` resolves and is TLS-terminated by nginx with a certificate that includes `api.example.com`
- Anonymous `healthz` and authenticated `/v1/platform/services` requests succeed through the public edge
- Health probe in `config/health-probe-catalog.json` passes

## Notes For The Next Assistant

- The FastAPI app must use `httpx.AsyncClient` with connection pooling for upstream requests; do not create a new client per request
- JWT validation must use the JWKS endpoint, not a static key; Keycloak rotates its signing keys periodically
- The `/v1/platform/topology` endpoint calls the Proxmox API directly; use the existing `lv3_automation@pve` credentials from OpenBao
- The API gateway catalog JSON schema must be validated by `scripts/validate_repository_data_models.py` — add a schema for `api-gateway-catalog.json`

## Outcome

- repository implementation landed earlier on `main` in repo release `0.101.0`
- live rollout completed on 2026-03-24 in platform version `0.114.2`
- the live platform now serves `https://api.example.com/healthz` and accepts authenticated bearer requests on `https://api.example.com/v1/platform/services`
- the rollout is recorded in [receipts/live-applies/2026-03-24-adr-0092-platform-api-gateway-live-apply.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/live-applies/2026-03-24-adr-0092-platform-api-gateway-live-apply.json)
