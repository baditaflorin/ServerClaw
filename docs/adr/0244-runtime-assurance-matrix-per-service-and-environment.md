# ADR 0244: Runtime Assurance Matrix Per Service And Environment

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The platform now manages more than fifty services across production, staging,
preview, rehearsal, and recovery-oriented environments. Existing ADRs already
cover health probes, uptime contracts, structured logs, public-surface scans,
portal auth, and synthetic replay, but they do not yet form one stage-aware
assurance model.

That leaves an uncomfortable gap: a service can be declared in catalogs and
still fail one or more operational truths a human cares about:

- the runtime does not actually exist where the catalog says it should
- the route exists but the real user journey does not work
- HTTPS is present but misconfigured
- logs are emitted locally but not queryable centrally
- staging or preview has no meaningful smoke path at all

## Decision

We will govern runtime assurance through a **service-by-environment assurance
matrix**.

Every active service in every active environment must declare its required
assurance class for:

- existence and runtime witness
- startup, readiness, liveness, and degraded-state proof
- authenticated and unauthenticated user journeys where applicable
- HTTPS and certificate posture where applicable
- log ingestion and central queryability
- stage-appropriate smoke verification
- publication and route truth

The follow-on ADRs in this bundle define the assurance mechanisms for each of
those dimensions.

## Consequences

**Positive**

- runtime truth becomes explicit instead of being inferred from scattered tools
- services can no longer claim to be “done” without the assurance dimensions
  their stage and exposure require
- operators get one consistent language for what has been proven and what has
  not

**Negative / Trade-offs**

- every service owner must maintain more explicit metadata
- assurance for low-risk or peripheral services still costs some operational
  attention

## Boundaries

- This ADR governs assurance contracts, not product-specific implementation
  details.
- Not every service needs every dimension; the matrix is stage-aware and
  exposure-aware rather than one-size-fits-all.

## Related ADRs

- ADR 0064: Health probe contracts for all services
- ADR 0123: Service uptime contracts and monitor-backed health
- ADR 0133: Portal authentication by default
- ADR 0142: Public surface automated security scan
- ADR 0169: Structured log field contract
- ADR 0190: Synthetic transaction replay for capacity and recovery validation
