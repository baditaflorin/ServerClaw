# ADR 0323: Service Mobility Tiers And Migration Waves For Runtime Pools

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-01

## Context

Not every service currently living on `docker-runtime-lv3` should be moved or
scaled the same way.

Treating all of them as equally movable would create avoidable risk:

- identity, secrets, workflow control, and internal coordination services are
  high-consequence anchors
- AI, OCR, notebooks, and heavy workers are bursty and are the strongest
  candidates for elastic placement
- operator and collaboration surfaces often can move, but usually still want a
  singleton contract

If the platform wants to decompose the current shared runtime safely, it needs a
mobility contract and an ordered migration plan.

## Decision

We will classify services into **mobility tiers** and move them through
**explicit migration waves**.

### Mobility tiers

- `anchor`: fixed-capacity or high-consequence services that stay on one pool
  until a reviewed migration window; not autoscaled
- `movable_singleton`: services that may change pools, but only one active
  instance is expected at a time
- `elastic_stateless`: services that may run multiple replicas across eligible
  pool members and participate in autoscaling
- `burst_batch`: queued, worker, notebook, or extraction workloads that may
  drain, pause, or preempt when the pool is protecting higher-priority services

### Migration waves

The first migration order is:

1. move lightweight operator and support surfaces from the legacy shared runtime
   into `runtime-general`
2. move memory-bursty AI, OCR, notebook, and heavy worker services into
   `runtime-ai`
3. move remaining product and application APIs into the appropriate pool after
   their dependencies are declared
4. revisit any control-plane anchors only after the earlier waves prove stable

### Governance rules

- every service must declare its mobility tier before it is moved out of the
  legacy shared runtime
- services without a declared tier are treated as anchors by default
- only `elastic_stateless` and `burst_batch` services are eligible for the
  autoscaling path from ADR 0322
- different migration waves may proceed in parallel only when their target pools
  differ and the dependency graph shows no shared mutable surface

## Consequences

**Positive**

- the platform gains a safer path off the current catch-all runtime instead of
  one risky big-bang move
- autoscaling eligibility becomes explicit and reviewable per service
- migration planning can be parallel where safe and deliberately serial where
  the blast radius is high

**Negative / Trade-offs**

- every service now needs another piece of metadata
- some services may remain on the legacy shared runtime longer than operators
  would like because they are anchors or have unresolved dependencies

## Boundaries

- This ADR governs mobility and migration order, not the exact new hostnames or
  products used by each service after migration.
- A service can change tiers later, but only through an explicit review rather
  than an emergency assumption during an incident.

## Related ADRs

- ADR 0154: VM-scoped parallel execution lanes
- ADR 0184: Failure-domain labels and anti-affinity policy
- ADR 0192: Separate capacity classes for standby, recovery, and preview workloads
- ADR 0205: Capability contracts before product selection
- ADR 0322: Memory-pressure autoscaling for elastic runtime pools
