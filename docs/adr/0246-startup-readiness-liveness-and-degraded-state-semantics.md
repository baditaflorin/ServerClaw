# ADR 0246: Startup, Readiness, Liveness, And Degraded State Semantics

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: not yet
- Implemented In Platform Version: 0.130.44
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

ADR 0064 established liveness and readiness contracts, but a large platform
needs a richer operational vocabulary than simple healthy or unhealthy.

Examples:

- a service may be starting and should not page as failed yet
- a service may be live but degraded because one optional dependency is missing
- a service may be ready for internal traffic but not for public traffic

## Decision

We will standardize four service-health semantics for runtime assurance:

- `startup`: process or container is initializing and not yet ready
- `ready`: the service can perform its declared primary function for the current
  stage
- `degraded`: the service is reachable but one or more declared capabilities are
  impaired
- `failed`: liveness or stage-required readiness is broken

### Required probe layering

- startup probes prove initialization completion without over-paging
- readiness probes prove stage-appropriate functionality
- liveness probes prove the process is still serving
- degraded-state rules prove when a service should stay visible but not be
  treated as healthy

## Consequences

**Positive**

- operators get more honest status than “running means healthy”
- dependency loss can be modeled without hiding partial availability
- different stages can require different readiness depth while sharing one core
  vocabulary

**Negative / Trade-offs**

- every service owner must define degraded-state rules intentionally
- dashboards and alerts become more nuanced than binary up/down

## Boundaries

- This ADR extends ADR 0064; it does not replace per-service probe contracts.
- Degraded status is not a convenient place to hide real failures; stage rules
  must define which impairments are tolerable.

## Related ADRs

- ADR 0064: Health probe contracts for all services
- ADR 0123: Service uptime contracts and monitor-backed health
- ADR 0196: Realtime metrics
- ADR 0244: Runtime assurance matrix per service and environment

## Live Apply Notes

- Live verification ran from rebased workstream commit
  `dc0624974fff094ff0f50a096ea5c411d64d53bf` by replaying the
  `windmill` and `api_gateway` runtime paths on `docker-runtime-lv3`, then
  rechecking the structured observation output and authenticated platform
  health endpoints for `api_gateway`, `platform_context_api`, and `windmill`.
- `Implemented In Repo Version` remains `not yet` until the protected release
  and canonical-truth files are updated during the final merge-to-main step.
