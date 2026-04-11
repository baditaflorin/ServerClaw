# ADR 0092: Unified Platform API Gateway

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.101.0
- Implemented In Platform Version: 0.114.2
- Implemented On: 2026-03-24
- Date: 2026-03-23

## Context

The platform currently exposes a patchwork of service-specific ports and URLs. Operators and agents interact with Windmill on port 8005, OpenBao on port 8200, step-ca on port 9443, NetBox on port 8004, and so on — each with its own authentication model, URL pattern, and client library. The control-plane communication lanes (ADR 0045) define which services talk to which, but there is no single authoritative API surface.

This creates several concrete problems:

- **Agent tool proliferation**: Every new service added to the platform requires a new agent tool definition (ADR 0069) with a hardcoded base URL. When a service moves VM or port, all agent tool definitions break simultaneously.
- **No unified authentication enforcement**: Some services are behind Keycloak OIDC (ADR 0056), some use service tokens, some use mTLS (ADR 0047). There is no single place to enforce that every API call is authenticated.
- **No versioning or deprecation path**: Service APIs are consumed directly; there is no layer to version-stabilise the interface before a service upgrade changes its API contract.
- **Ops portal fragility**: The ops portal (ADR 0074) and the platform CLI (ADR 0090) both embed service base URLs as configuration; these drift as services evolve.
- **No cross-cutting observability**: Request logs, latency metrics, and error rates exist per-service but cannot be aggregated into a single API health view.

The platform has all the building blocks: Keycloak for identity, OpenBao for secrets, NATS for events, Windmill for orchestration. What is missing is a thin, durable aggregation layer that gives everything a single front door.

## Decision

We will deploy a **platform API gateway** on `docker-runtime` as a FastAPI-based aggregation and proxy service, exposed on the host at `http://10.10.10.20:8083` and published at `https://api.example.com` via the nginx edge (ADR 0021). TLS terminates at the edge; bearer-token authentication is enforced by the gateway itself.

### Architecture

```
external clients / agents / ops portal
        │
        ▼
  api.example.com:443  (nginx edge, TLS termination only)
        │
        ▼
  10.10.10.20:8083  (published api-gateway runtime on docker-runtime)
        │
   ┌────┴──────────────────────────────────┐
   │  FastAPI facade  (routes + OpenAPI)   │
   └────┬──────────────────────────────────┘
        │ service routes
        ├── /v1/windmill/*    → windmill:8005
        ├── /v1/openbao/*     → openbao:8200
        ├── /v1/netbox/*      → netbox:8004
        ├── /v1/nats/*        → nats:4222  (HTTP bridge)
        ├── /v1/platform/*    → FastAPI platform endpoints
        └── /v1/health        → aggregate health check
```

### FastAPI gateway

The facade is a thin Python FastAPI application (`scripts/api_gateway/main.py`) that:

1. **Authenticates** bearer-protected requests against the Keycloak JWKS endpoint, extracting the caller identity and roles, while keeping `/healthz` anonymous for liveness.
2. **Routes** the request to the appropriate upstream service using `httpx` with connection pooling.
3. **Strips** service-internal headers before forwarding; adds `X-Gateway-Request-ID` and `X-Caller-Identity` headers.
4. **Emits** a NATS event `platform.api.request` for every request (async, non-blocking) with method, path, status, latency, and caller identity — enabling the mutation audit log (ADR 0066) to capture API-level mutations.
5. **Exposes** a machine-readable OpenAPI schema at `/v1/openapi.json` that aggregates the schemas of all registered upstream services.

### Service registration

Services are registered in `config/api-gateway-catalog.json`:

```json
{
  "services": [
    {
      "id": "windmill",
      "upstream": "http://windmill:8005",
      "gateway_prefix": "/v1/windmill",
      "auth": "keycloak_jwt",
      "required_role": "platform-operator",
      "strip_prefix": true,
      "timeout_seconds": 30
    },
    {
      "id": "openbao",
      "upstream": "http://openbao:8200",
      "gateway_prefix": "/v1/openbao",
      "auth": "keycloak_jwt",
      "required_role": "platform-operator",
      "strip_prefix": true,
      "timeout_seconds": 10
    },
    {
      "id": "platform",
      "upstream": "local",
      "gateway_prefix": "/v1/platform",
      "auth": "keycloak_jwt",
      "required_role": "platform-read",
      "strip_prefix": false,
      "timeout_seconds": 5
    }
  ]
}
```

This catalog is the single source of truth. The agent tool registry (ADR 0069), the ops portal (ADR 0074), and the platform CLI (ADR 0090) all derive service URLs from this catalog rather than embedding them directly.

### Native platform endpoints

The FastAPI facade exposes first-class endpoints under `/v1/platform/` that do not proxy to an upstream service. These are the primary interface for agents and automation:

| Endpoint | Method | Description |
|---|---|---|
| `/v1/platform/health` | GET | Aggregate health of all registered services |
| `/v1/platform/services` | GET | List services from the capability catalog |
| `/v1/platform/drift` | GET | Latest drift report summary |
| `/v1/platform/topology` | GET | Live VM topology from Proxmox API |
| `/v1/platform/deploy` | POST | Trigger a deployment via Windmill |
| `/v1/platform/secrets/rotate` | POST | Trigger secret rotation for a service |

### Compose service definition

```yaml
services:
  api-gateway:
    image: registry.example.com/platform/api-gateway:latest
    ports:
      - "8080:8080"
    environment:
      KEYCLOAK_JWKS_URL: "http://keycloak:8080/realms/lv3/protocol/openid-connect/certs"
      NATS_URL: "nats://nats:4222"
      GATEWAY_CATALOG: "/config/api-gateway-catalog.json"
    volumes:
      - ./config:/config:ro
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
```

### Grafana dashboard

A dedicated **Platform API** Grafana dashboard tracks:
- Request rate by service and caller
- p50/p95/p99 latency per upstream
- Error rate (4xx, 5xx) per service
- Active connections per upstream

## Consequences

**Positive**
- All platform API calls are authenticated at a single chokepoint; no service can be accidentally called without a valid Keycloak JWT
- Agent tools and the ops portal only need to know `api.example.com`; upstream service URLs are entirely internal implementation detail
- The OpenAPI schema at `/v1/openapi.json` is auto-discoverable by agents (ADR 0069) and can drive code generation
- Cross-service latency and error rates are visible in a single Grafana dashboard
- Adding a new service to the platform adds one entry to `config/api-gateway-catalog.json` rather than updating every consumer

**Negative / Trade-offs**
- The gateway is a new single point of failure; it must be deployed with a health probe (ADR 0064) and monitored
- Proxying adds one network hop and ~1–2ms latency per request; acceptable for platform operations, not for database queries (which remain direct)
- Services that use binary protocols (OpenBao Agent auto-auth, step-ca TLS bootstrapping) cannot be proxied by this gateway; they remain direct

## Implementation Notes

- Live rollout completed on 2026-03-24 in platform version `0.114.2` with receipt [receipts/live-applies/2026-03-24-adr-0092-platform-api-gateway-live-apply.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/receipts/live-applies/2026-03-24-adr-0092-platform-api-gateway-live-apply.json).
- The live runtime now validates JWTs against Keycloak over the shared Docker network, publishes the gateway on host port `8083`, and verifies an authenticated `/v1/platform/services` request during the Ansible converge.
- Live verification on 2026-03-24 confirmed `https://api.example.com/healthz` returned `200 {"status":"ok"}` and `https://api.example.com/v1/platform/services` returned `200` with a valid realm-issued bearer token.
- Repo version `0.162.0` extends the gateway with ADR 0166 canonical error envelopes, shared registry-backed error codes, and trace-id-aware failure responses.

## Alternatives Considered

- **Kong or Traefik as API gateway**: mature products but heavyweight for a single-node homelab; require their own data stores or complex configuration management
- **Nginx as reverse proxy only**: no auth enforcement, no OpenAPI aggregation, no NATS event emission; solves routing but not the other problems
- **No gateway; just update all consumers when services move**: this is the current state; it is the problem being solved

## Related ADRs

- ADR 0021: Public subdomain publication (nginx edge that fronts the gateway)
- ADR 0045: Control-plane communication lanes (defines the upstream topology)
- ADR 0047: Short-lived credentials and mTLS (used between edge and gateway)
- ADR 0056: Keycloak SSO (provides the JWT that the gateway validates)
- ADR 0058: NATS JetStream (receives `platform.api.request` events)
- ADR 0066: Mutation audit log (consumes gateway events for API mutations)
- ADR 0069: Agent tool registry (derives service URLs from the gateway catalog)
- ADR 0074: Ops portal (calls gateway `/v1/platform/*` endpoints)
- ADR 0090: Unified platform CLI (routes commands through the gateway)
