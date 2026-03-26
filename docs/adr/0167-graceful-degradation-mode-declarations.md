# ADR 0167: Graceful Degradation Mode Declarations

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.146.1
- Implemented In Platform Version: 0.130.15
- Implemented On: 2026-03-26
- Date: 2026-03-25

## Context

Every platform service depends on other systems. When one of those dependencies is unavailable, the current platform behaviour is uneven: some services time out, some fail hard, and some continue in ways that are not visible to operators. There is no canonical answer to questions such as:

- what does the platform API do while Keycloak is unavailable?
- what happens to request events when NATS publication fails?
- which dependency failures are expected to degrade a service instead of taking it fully down?

Without explicit declarations, dependency failures look like ad hoc outages. Operators have to infer intent from logs or retry behaviour instead of reading it from a controlled contract.

## Decision

We will make graceful degradation a declared and testable part of the platform contract.

### Service-catalog declarations

Each service may declare one or more `degradation_modes` in `config/service-capability-catalog.json`. A declaration records:

- the dependency that can fail
- whether that dependency is `hard`, `soft`, or `optional`
- the degraded behaviour operators should expect
- the maximum intended degraded window
- the recovery signal that should clear the degraded state
- the `fault:*` scenario that verifies the declaration

### First implemented runtime

The first live runtime implementation is the platform API gateway:

- for `keycloak`, the gateway continues using cached JWKS while the cache is still valid; once the cache expires, auth-gated requests fail fast with `503` and `Retry-After: 30`
- for `nats`, the gateway writes request events into a durable local outbox under `/data/nats-outbox.jsonl` and flushes them automatically once publication succeeds again

### Operator-visible degraded state

Active degraded modes are written to a repo-managed state file and surfaced through:

- `platform/health/composite.py`
- `/v1/platform/services`
- `/v1/platform/health`
- `/v1/platform/degradations`

This makes degraded operation visible as a deliberate state, not just an indirect symptom.

## Consequences

### Positive

- degradation behaviour is now part of a validated contract instead of tribal knowledge
- the gateway can continue operating through bounded dependency failures without pretending the system is fully healthy
- operators can distinguish an expected degraded mode from generic drift or probe failure

### Negative / Trade-offs

- the current durable outbox is gateway-local, not yet a shared platform-wide event buffer
- only the first runtime slice is implemented in this ADR: future services still need to adopt the same declaration and surfacing pattern
- cached authentication material trades freshness for bounded continuity during an outage

## Boundaries

- this ADR governs platform-layer dependency declarations and the runtime surfaces that consume them
- it does not by itself implement a shared distributed circuit-breaker runtime for every service
- application-internal failure handling remains the responsibility of the owning service

## Implementation Notes

- `docs/schema/service-capability-catalog.schema.json` and `scripts/service_catalog.py` now validate and render `degradation_modes`
- `scripts/api_gateway/main.py` records live degraded state, serves cached JWKS while valid, returns explicit `503` responses after cache expiry, and buffers NATS events locally on failure
- `platform/degradation/state.py` provides the repo-managed degraded-state store
- `platform/health/composite.py` and the API gateway platform endpoints surface active degraded modes to operators

## Related ADRs

- ADR 0075: Service capability catalog
- ADR 0092: Platform API gateway
- ADR 0128: Platform health composite index
