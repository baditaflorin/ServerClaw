# ADR 0251: Stage-Scoped Smoke Suites And Promotion Gates

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.177.84
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Not every environment needs the same level of proof, but every meaningful stage
needs some level of smoke verification.

Today, smoke coverage is uneven:

- some services have good replay or probe coverage
- others rely on convergence success alone
- stage promotion can happen without one declared human-meaningful smoke path

## Decision

We will require **stage-scoped smoke suites** for active services and wire them
into promotion and deployment gates.

### Stage expectations

- preview: minimal route and primary capability smoke proof
- staging: representative human or API smoke path for declared stage-ready
  services
- production: smoke proof for the user-facing or operator-facing primary path,
  plus rollback-safe verification

### Gate rule

- a service may not claim a stage-ready status without at least one declared
  smoke suite for that stage
- promotion and post-deploy verification must surface smoke failures as
  first-class blockers, not informational noise

## Consequences

**Positive**

- “works in this stage” becomes testable rather than rhetorical
- services with weak verification become visible early
- deployments gain more user-meaningful proof than raw process startup

**Negative / Trade-offs**

- service teams must maintain smoke scenarios as the product evolves
- smoke suites can become flaky if they are not deliberately scoped

## Boundaries

- Smoke suites do not replace synthetic replay, integration tests, or probes.
- A stage may keep smaller smoke expectations than production, but it may not
  have zero assurance by default.

## Related ADRs

- ADR 0111: End-to-end integration test suite
- ADR 0190: Synthetic transaction replay for capacity and recovery validation
- ADR 0214: Production and staging cells as the unit of high availability
- ADR 0244: Runtime assurance matrix per service and environment
