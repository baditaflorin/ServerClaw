# ADR 0180: Standby Capacity Reservation and Placement Rules

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.176.4
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-26

## Context

Redundancy fails in practice when standby capacity is planned only on paper. A warm standby that has no reserved CPU, memory, disk, or placement rule is just a future outage. On a single Proxmox host, this matters even more because all standbys compete for the same finite resources.

The platform needs explicit rules for where standbys may live, how much spare capacity must exist, and which failure modes a standby is expected to cover.

## Decision

We will reserve standby capacity and define placement rules for any service declared as `R2` or higher in ADR 0179.

### Reservation policy

For every `R2` service, the platform must reserve enough spare resources to bring up the standby without emergency resizing:

- CPU reservation target
- memory reservation target
- storage class and minimum free capacity
- required network attachment

### Placement rules

- primary and standby may not share the same compose project or container namespace
- when possible, primary and standby should not share the same guest VM
- standby data paths must be distinct from primary data paths
- backup may host passive control-plane standbys only if the role does not compromise backup integrity

### Failure-domain honesty

Standbys on the same Proxmox host improve recovery from guest or software faults, not host loss. All documentation must state that clearly.

## Consequences

**Positive**

- Warm standby claims become believable because required headroom is reserved.
- Placement decisions are reviewable instead of ad hoc.
- Capacity planning aligns with redundancy goals.

**Negative / Trade-offs**

- Reserved capacity lowers apparent utilization efficiency.
- Some desired standbys may be deferred until additional hardware exists.

## Boundaries

- This ADR does not choose which services need standbys; ADR 0179 does that.
- Placement rules do not replace tested failover procedures.

## Related ADRs

- ADR 0029: Dedicated backup VM with local PBS
- ADR 0105: Platform capacity model and resource quota enforcement
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0179: Service redundancy tier matrix
