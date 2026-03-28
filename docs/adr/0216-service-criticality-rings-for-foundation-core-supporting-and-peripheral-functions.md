# ADR 0216: Service Criticality Rings For Foundation, Core, Supporting, And Peripheral Functions

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ADR 0179 already defines redundancy tiers such as `R0` through `R3`, but
redundancy tier alone does not answer a different operations question:

- which services must come back first
- which dependencies are allowed to pull others down with them
- which services are truly central versus helpful but deferrable

The platform needs a clear answer that is better aligned than the informal
"core" versus "peripheral" language.

## Decision

We will classify services into **criticality rings**. Rings express recovery and
dependency priority, not just redundancy mechanics.

### Rings

- `foundation`: services required to establish trust, operator control, and
  authoritative data recovery
- `core`: services required for normal platform control and production-facing
  operation once the foundation exists
- `supporting`: services that materially improve operations but are not required
  to restore foundation and core
- `peripheral`: convenience, experimental, or low-blast-radius services that
  can be deferred during restore and failover

### Dependency rule

Dependency direction must be inward:

- `peripheral` may depend on `supporting`, `core`, or `foundation`
- `supporting` may depend on `core` or `foundation`
- `core` may depend on `foundation`
- `foundation` may not require `core`, `supporting`, or `peripheral` to recover

### Operational rule

Recovery, failover rehearsal, and staging parity investments are prioritized in
ring order:

1. `foundation`
2. `core`
3. `supporting`
4. `peripheral`

Criticality ring and redundancy tier are orthogonal. A service can be
`foundation` and still only have an `R1` implementation today if capacity is not
there yet, but that gap must remain visible.

## Consequences

**Positive**

- "core" and "peripheral" become part of a fuller, more precise vocabulary.
- Bring-up order and failover priorities become explicit.
- Dependency drift becomes easier to spot because inward-only dependencies are
  reviewable.

**Negative / Trade-offs**

- Some current services may need difficult reclassification discussions.
- The platform will have to admit when a high-criticality service still has a
  weak redundancy posture.

## Boundaries

- This ADR does not replace redundancy tiers, RTO/RPO targets, or capacity
  classes.
- The ring model is about service priority and dependency direction, not about
  whether a service is public, private, or staging-only.

## Related ADRs

- ADR 0100: Formal RTO/RPO targets and disaster recovery playbook
- ADR 0179: Service redundancy tier matrix
- ADR 0188: Failover rehearsal gate for redundancy tiers
- ADR 0208: Dependency direction and composition roots
- ADR 0209: Use-case services and thin delivery adapters
