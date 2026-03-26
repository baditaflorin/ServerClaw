# ADR 0179: Service Redundancy Tier Matrix

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-26

## Context

The platform currently runs on one dedicated Hetzner host. That makes "high availability" an easy phrase to misuse. Some redundancy is still valuable:

- warm replicas for software or operator fault recovery
- cold standby definitions that speed rebuild
- off-host copies of control metadata
- clear restore expectations per service

What is missing is a single classification that says which services merit which level of redundancy and what that means operationally.

## Decision

We will classify all platform services into a **redundancy tier matrix**. The tier determines the required recovery assets, replica expectations, and failover procedure.

### Tiers

- `R0`: rebuild from git and backups only
- `R1`: cold standby, automated rebuild, verified restore
- `R2`: warm standby on a separate VM with current data replication
- `R3`: active/passive or active/active across separate failure domains

### Current host constraint

On the current single-host platform:

- `R2` may protect against guest-level corruption or operator mistakes
- `R3` is a design target only and is not considered implemented until a second failure domain exists

### Required declaration

Each managed service must declare:

- redundancy tier
- RTO/RPO target
- backup source
- replica or standby location
- failover trigger
- failback method

## Consequences

**Positive**

- Redundancy discussions become concrete and scoped by service.
- The team can prioritize backup, standby, and replication work where it matters most.
- The repository stops implying the same resiliency promise for every component.

**Negative / Trade-offs**

- Some services will explicitly remain low-redundancy for a while.
- Tier declarations create pressure to verify implementation regularly.

## Boundaries

- This ADR classifies resilience targets; it does not itself implement replicas or failover.
- A service cannot claim an implemented tier above what the current failure domains support.

## Related ADRs

- ADR 0029: Dedicated backup VM with local PBS
- ADR 0099: Automated backup restore verification
- ADR 0100: RTO/RPO targets and disaster recovery playbook
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0181: Off-host witness and control metadata replication
