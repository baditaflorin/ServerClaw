# ADR 0252: Route And DNS Publication Assertion Ledger

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: pending merge to main
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

For a service with many environments and exposure modes, “it exists” still does
not prove “users reach the right thing”.

The platform needs explicit proof that:

- DNS resolves where the catalog says
- the edge or private route points at the declared service
- the public hostname, private hostname, and environment lane are not crossed
  accidentally

## Decision

We will maintain a **route and DNS publication assertion ledger** for all
published or operator-reachable service endpoints.

### Required assertions

- declared hostname to declared publication class
- declared hostname to declared environment
- declared route target to declared service identity
- declared audience to declared auth requirement

### Evidence sources

- DNS resolution checks
- edge publication config checks
- protocol probes from the correct network vantage point
- deployment receipts that confirm the route target was converged

## Consequences

**Positive**

- services can no longer silently drift onto the wrong hostname or environment
- publication bugs become traceable as route-assertion failures instead of vague
  reachability complaints
- private, operator-only, and public routes can share one truth model

**Negative / Trade-offs**

- the route ledger adds another generated artifact to keep current
- complex shared-edge setups need careful modeling so assertions stay readable

## Boundaries

- This ADR governs route and publication truth, not application content or auth
  journey correctness.
- Unpublished background services may remain outside this ledger if they have no
  operator or user endpoint.

## Related ADRs

- ADR 0021: Public subdomain publication through the NGINX edge
- ADR 0076: Subdomain governance
- ADR 0133: Portal authentication by default
- ADR 0217: One-way environment data flow and replication authority
- ADR 0244: Runtime assurance matrix per service and environment
