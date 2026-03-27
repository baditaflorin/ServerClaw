# ADR 0184: Failure-Domain Labels and Anti-Affinity Policy

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-27

## Context

The repository already describes primaries, standbys, fixtures, and restore drills, but placement intent is still mostly implicit. Without explicit failure-domain metadata, the platform can accidentally place related workloads too close together:

- a primary and standby on the same host or storage path
- a restore drill on the same bridge and VM as the service being validated
- preview environments consuming the very headroom reserved for failover

As the platform adds auxiliary cloud capacity, the gap becomes more serious: it is no longer enough to say "separate" without describing what separate means.

## Decision

We will require **failure-domain labels** and **anti-affinity declarations** for all managed primaries, standbys, restore targets, and ephemeral pools.

### Required metadata

Each relevant object must declare:

- `failure_domain`: for example `host:proxmox_florin`, `cloud:hetzner-fsn1`
- `placement_class`: `primary`, `standby`, `recovery`, `preview`, or `fixture`
- `anti_affinity_group`: logical grouping that must not be co-located when alternatives exist
- `co_location_exceptions`: explicit waivers with rationale

### Policy rules

- A `primary` and its `standby` must not share a `failure_domain` when another declared domain exists.
- A `recovery` target may not land on the same guest or storage path as the protected workload.
- `preview` and `fixture` placements may not evict or crowd out `standby` reservations.
- Waivers for same-domain placement must be recorded as temporary, visible debt rather than silent defaults.

### Reviewability

Placement decisions become reviewable repository truth. Every redundancy claim, failover drill, and preview allocation should be explainable from committed metadata rather than inferred from runtime luck.

## Consequences

**Positive**

- HA claims become auditable instead of hand-wavy.
- Future schedulers and allocators can consume the same placement facts.
- Restore and test environments become less likely to invalidate the thing they are supposed to verify.

**Negative / Trade-offs**

- More metadata must be maintained for each service and environment.
- In the current single-host phase, many declarations will initially carry same-domain waivers until the auxiliary domain is available.

## Boundaries

- This ADR defines placement metadata and policy, not the allocator implementation.
- Anti-affinity is only as strong as the declared failure domains; dishonest labels still produce dishonest outcomes.

## Related ADRs

- ADR 0088: Ephemeral infrastructure fixtures
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0179: Service redundancy tier matrix
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0183: Auxiliary cloud failure domain for witness, recovery, and burst capacity
