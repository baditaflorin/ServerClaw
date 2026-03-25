# ADR 0164: Circuit Breaker Pattern for External Service Calls

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.152.0
- Implemented In Platform Version: 0.130.5
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The platform makes synchronous calls to several external and internal services on the critical path of agent execution:

- **Keycloak** (`sso.lv3.org`): JWT validation on every API gateway request; JWKS refresh every 300 seconds.
- **OpenBao** (Proxmox host, Tailscale-only): Secret reads at workflow start and during rotation.
- **Windmill** (`docker-runtime-lv3`): Job submission and status polling for every intent execution.
- **Hetzner DNS API** (external): DNS record updates during subdomain provisioning.
- **NATS** (`docker-runtime-lv3`): Every platform event publication.
- **Anthropic/Ollama API**: Every LLM inference call in agent workflows.

The current error handling model from ADR 0163 handles transient failures with retries and backoff. It does not handle dependency outages well: when a dependency is fully unavailable, each caller burns the same timeout and retry budget before independently discovering the outage.

The correct model for service outages is the **circuit breaker pattern**:

- **CLOSED**: calls pass through and failures are counted.
- **OPEN**: calls fail immediately without attempting a connection.
- **HALF_OPEN**: after a recovery window, a probe call is allowed through and closes the circuit if it succeeds.

A circuit breaker turns "wait 30 seconds to rediscover Keycloak is down on every request" into "fail immediately after the configured threshold has already established the outage."

## Decision

We implement a shared, repo-managed **circuit breaker layer** for external and high-impact internal service calls.

The first integrated repository implementation lands in:

- `platform/circuit/` for policy loading, state backends, and sync plus async breaker wrappers
- `config/circuit-policies.yaml` as the canonical circuit contract
- `scripts/api_gateway/main.py` for Keycloak JWKS fetches, proxied upstream calls, and gateway-side NATS request-event publishing
- `platform/llm/client.py` for Ollama and fallback LLM calls
- `platform/scheduler/scheduler.py` and `scripts/runbook_executor.py` for Windmill-facing execution paths
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/` so the gateway converge path bundles the circuit policy file

### Circuit breaker state machine

```text
  CLOSED --(failure threshold exceeded)--> OPEN
    ^                                      |
    |                                      |
    +--(probe succeeds)---- HALF_OPEN <----+
                ^             |
                +--(recovery window elapsed)
```

### Distributed and local circuit state

The preferred shared state backend is NATS JetStream KV. The implementation uses the `platform-circuits` KV bucket when `LV3_NATS_URL` or an equivalent circuit-state NATS URL is configured.

When NATS is unavailable or not configured, the circuit layer falls back to:

- a JSON file backend when `LV3_CIRCUIT_STATE_FILE` is set
- otherwise, local in-memory state inside the process

That keeps the implementation deployable in both the distributed runtime and local test harnesses without inventing ad hoc state stores.

### Circuit policy per service

`config/circuit-policies.yaml` is the single source of truth for circuit thresholds, recovery windows, and success thresholds.

The initial integrated policy set covers:

- `keycloak`
- `openbao`
- `windmill`
- `nats`
- `hetzner_dns`
- `anthropic_api`
- `ollama`

### Integrated callers

The initial repository implementation wraps these concrete dependency paths:

- Keycloak JWKS fetches in the API gateway
- proxied API gateway upstream service calls
- gateway-side NATS request-event publishing
- local Ollama model discovery and generation
- fallback external LLM completions
- Windmill job submission and status paths in the scheduler and runbook executor

### Operator-facing behaviour

When a dependency circuit is open:

- the API gateway returns `503` with `Retry-After`
- the shared LLM client falls back to the configured alternate provider without repeatedly burning the primary timeout budget
- Windmill-facing callers fail fast instead of repeatedly attempting the same unavailable endpoint

## Consequences

**Positive**

- repeated dependency outages stop consuming the same timeout budget on every request
- the platform fails faster and more predictably during Keycloak, Windmill, Ollama, or NATS outages
- policy values are centralized in one repo-managed contract instead of being duplicated across callers
- the gateway converge path now bundles the circuit policy file so live rollout can use the same config

**Negative / Trade-offs**

- circuits can open too aggressively if thresholds are tuned poorly
- when NATS is unavailable, processes fall back to local state and may temporarily disagree about circuit status
- the first integrated implementation does not yet implement the deeper queueing and buffering behaviors described in ADR 0167

## Boundaries

- circuit breakers govern platform code paths, not raw Ansible SSH transport or Proxmox VM networking
- this ADR implements fail-fast protection and shared policy management; it does not, by itself, claim a completed live rollout
- graceful degradation side effects such as intent queueing or outbox flushing remain covered by later work

## Related ADRs

- ADR 0058: NATS event bus
- ADR 0092: Platform API gateway
- ADR 0119: Budgeted workflow scheduler
- ADR 0129: Runbook automation executor
- ADR 0145: Ollama
- ADR 0163: Retry taxonomy
- ADR 0167: Graceful degradation mode declarations
