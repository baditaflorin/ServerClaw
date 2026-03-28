# ADR 0223: Canonical HA Topology Catalog And Reusable Automation Profiles

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

This ADR bundle introduces more useful structure:

- environment cells
- node roles
- service criticality rings
- data-authority direction
- per-data-class replication rules
- bootstrap sequencing
- failover endpoint semantics

That structure only helps if it stays DRY. If every new playbook, inventory
file, and health check re-encodes the same HA intent in slightly different
shapes, the architecture will rot into duplication.

## Decision

We will centralize HA and replication intent in one **canonical topology
catalog** with reusable automation profiles derived from it.

### Minimum catalog fields

Every managed service should eventually declare:

- owning environment cell
- node role or node pool
- service criticality ring
- redundancy tier
- data class
- replication mode
- failover authority
- bootstrap phase
- write, read, management, and optional bootstrap endpoints
- recovery profile and evidence requirements

### Reusable profiles

Automation should consume shared profiles for recurring patterns such as:

- stateless edge publication
- control-plane authority with standby metadata copy
- single-writer relational primary with warm standby
- queue or stream cluster
- derived search or vector index
- backup and restore target
- staging shadow service seeded from sanitized production data

### DRY rule

No service should invent a bespoke HA structure if an existing profile already
fits. When a true exception exists, the repository should extend the shared
profile set rather than scattering one-off logic across inventories, playbooks,
and scripts.

## Consequences

**Positive**

- HA architecture becomes reusable instead of copy-pasted.
- Validation can detect drift between declared intent and generated automation.
- Future assistants get one canonical source of truth instead of seven partial
  ones.

**Negative / Trade-offs**

- The catalog will need careful schema design to stay readable.
- Some existing files will eventually need refactoring to consume shared
  profiles rather than their current bespoke logic.

## Boundaries

- This ADR does not define the exact schema file name or generator layout; it
  sets the architectural expectation.
- DRY does not mean over-generalized abstractions. Profiles should exist only
  where they remove real duplication and improve reviewability.

## Related ADRs

- ADR 0062: Role composability and metadata-driven reuse
- ADR 0075: Service capability catalog
- ADR 0173: Ownership manifest for parallel workstreams
- ADR 0205: Capability contracts before product selection
- ADR 0214: Production and staging cells as the unit of high availability
