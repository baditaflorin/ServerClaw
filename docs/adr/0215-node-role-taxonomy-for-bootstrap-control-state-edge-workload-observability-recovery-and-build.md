# ADR 0215: Node Role Taxonomy For Bootstrap, Control, State, Edge, Workload, Observability, Recovery, And Build

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The platform already has guests with recognizable responsibilities such as
`nginx-lv3`, `postgres-lv3`, `docker-runtime-lv3`, `monitoring-lv3`, and
`backup-lv3`, but the repository still lacks one standard node-role vocabulary.

That gap shows up whenever people describe the estate informally:

- some machines are described as "init" servers
- some are described as "core"
- some are described as "peripheral"
- some are described by the current service installed on them rather than by
  their platform role

That language is not precise enough for separation of concerns, placement
policy, or reusable automation.

## Decision

We will classify every server, VM, and future node pool by **primary node role**.

### Standard roles

- `bootstrap`: first-boot, trust bootstrap, image seeding, and bring-up helpers
- `control`: identity, secrets, orchestration, service discovery, and platform
  coordination
- `state`: authoritative mutable state such as relational databases, queues,
  object stores, and secret authorities
- `edge`: ingress, reverse proxying, public publication, and traffic entry
- `workload`: application runtimes, internal APIs, and long-running workers
- `observability`: monitoring, logging, tracing, and alerting
- `recovery`: backup targets, restore verification, warm standbys, and drill
  controllers
- `build`: CI runners, image builds, artifact assembly, and disposable test
  execution

### Assignment rules

- Every node must declare exactly one primary role.
- A secondary role is allowed only when the current platform size forces role
  collapse and the exception is documented.
- `state` nodes must not also be primary `edge` or `build` nodes.
- `recovery` nodes must not carry sole production-primary state.
- `build` nodes are treated as noisy and low-trust compared with `control` and
  `state` nodes.

### Environment symmetry

Production and staging should use the same role taxonomy even when the staging
cell is smaller. A collapsed staging node is still tagged with the roles it is
temporarily combining so the technical debt remains visible.

## Consequences

**Positive**

- "init", "core", and "peripheral" are replaced by standard operations-facing
  terms with clearer placement meaning.
- Inventory, host variables, and automation profiles can group nodes by role
  without coupling to today's hostnames.
- Separation-of-concerns rules become enforceable rather than conversational.

**Negative / Trade-offs**

- Existing hosts may need multi-role waivers until capacity expands.
- More explicit metadata means more upfront design work for new services.

## Boundaries

- This ADR defines node vocabulary, not service criticality. A peripheral
  service can still run on a `workload` node if that is the correct platform
  role.
- This ADR does not prohibit small-footprint co-location when capacity is
  constrained; it requires those compromises to be explicit.

## Related ADRs

- ADR 0072: Staging and production environment topology
- ADR 0176: Inventory sharding for multi-agent execution
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0184: Failure-domain labels and anti-affinity policy
- ADR 0192: Separate capacity classes for standby, recovery, and preview
  workloads
