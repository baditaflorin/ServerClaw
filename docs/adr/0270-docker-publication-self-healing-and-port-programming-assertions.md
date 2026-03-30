# ADR 0270: Docker Publication Self-Healing And Port-Programming Assertions

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.93
- Implemented In Platform Version: 0.130.62
- Implemented On: 2026-03-30
- Date: 2026-03-28

## Context

Recovery receipts for Keycloak and related services exposed a fragile control
plane assumption: a container restart is not enough if Docker has lost its
publication state. Missing NAT chains or broken port programming can leave the
application healthy inside the guest while ingress is still dead.

That means service health can look green while user-facing recovery is still
broken.

## Decision

We will add **Docker publication self-healing** and **port-programming
assertions** for managed Docker guests.

### Required assertions

- expected bridge networks exist
- expected port publications are programmed
- required packet-filtering or NAT hooks exist for the current host mode
- published services answer from the intended bind address and port

### Healing rules

- self-heal may repair missing publication primitives before declaring a service
  healthy
- container recreation must be governed and targeted, not a blanket host reset
- readiness may not report healthy until both the application and its declared
  publication path succeed

## Consequences

**Positive**

- publication failures become detectable and repairable as first-class incidents
- service health better matches what operators and users actually experience
- emergency container restarts become less guess-driven

**Negative / Trade-offs**

- publication probes and repair logic increase Docker guest complexity
- healing logic must stay careful not to flap healthy services

## Boundaries

- This ADR governs Docker-hosted publication correctness inside managed guests.
- It does not replace shared edge or DNS publication policy.

## Related ADRs

- ADR 0023: Docker runtime VM baseline
- ADR 0024: Docker guest security baseline
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0246: Startup, readiness, liveness, and degraded-state semantics
