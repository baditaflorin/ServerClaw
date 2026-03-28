# ADR 0221: Role-Based Node Pools And Placement Boundaries

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ADR 0215 defines the node-role vocabulary, but the platform also needs a target
placement policy that says when those roles must live on different servers or
node pools.

Without that rule, small-footprint exceptions tend to harden into default
architecture:

- public edge services remain too close to primary state
- noisy builds land beside control-plane authorities
- backups and standbys share the same pool as the thing they are meant to
  protect

## Decision

We will use **role-based node pools** with explicit placement boundaries.

### Target pools

The target architecture allows dedicated pools for:

- `bootstrap_control`
- `state`
- `edge`
- `workload`
- `observability`
- `recovery`
- `build`

### Mandatory boundaries

- `state` pools must not host primary `edge` or `build` workloads.
- `recovery` pools must not be the same pool that carries the sole protected
  primary.
- `control` authorities should not depend on `build` pool availability.
- When separate pools exist, production and staging primaries must not share the
  same `state` pool.
- Internet-published ingress must terminate in the `edge` pool, not on
  authority-bearing `state` nodes.

### Small-platform waiver rule

When capacity forces pool collapse, the repository must record:

- which pools are combined
- why the exception exists
- what risk it introduces
- what future change removes the waiver

## Consequences

**Positive**

- Separation of concerns becomes a placement rule instead of a hopeful habit.
- Growth from one host to multiple nodes can follow a planned shape.
- Production and staging isolation become easier to reason about during future
  scale-out.

**Negative / Trade-offs**

- Honest pool separation increases hardware and operational cost.
- The current platform will carry visible waivers until more capacity exists.

## Boundaries

- This ADR sets the target placement policy; it does not by itself create new
  VMs or host groups.
- Node pools are a deployment concern and do not replace service-level
  redundancy or recovery requirements.

## Related ADRs

- ADR 0179: Service redundancy tier matrix
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0183: Auxiliary cloud failure domain for witness, recovery, and burst
  capacity
- ADR 0184: Failure-domain labels and anti-affinity policy
- ADR 0215: Node role taxonomy for bootstrap, control, state, edge, workload,
  observability, recovery, and build
