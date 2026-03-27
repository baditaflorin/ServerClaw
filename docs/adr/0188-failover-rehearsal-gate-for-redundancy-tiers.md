# ADR 0188: Failover Rehearsal Gate for Redundancy Tiers

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-27

## Context

ADR 0179 defines redundancy tiers, ADR 0098 defines HA for Postgres, and ADR 0099 verifies restores. What is still missing is a repeatable rule that says when a redundancy promise has been proven recently enough to remain trustworthy.

A redundancy design that is never rehearsed eventually becomes fiction:

- failover commands drift
- health checks stop matching reality
- standbys fall behind silently
- operators forget which path is authoritative

## Decision

We will require **scheduled failover or recovery rehearsals** for services that claim redundancy tiers above rebuild-only recovery.

### Rehearsal rules

- `R1` services must pass restore-to-preview rehearsal on a defined cadence.
- `R2` services must pass standby switchover or promotion rehearsal on a defined cadence.
- `R3` services must pass cross-domain failover rehearsal before they can claim implemented status.

### Gate effect

A service may keep its design tier, but its **implemented tier claim** is downgraded in status reporting if the required rehearsal has not passed within the declared freshness window.

### Evidence

Each rehearsal must publish:

- trigger and target environment
- duration and observed RTO
- data-loss or lag observation
- health verification results
- rollback or failback result

## Consequences

**Positive**

- Redundancy status becomes tied to evidence, not only architecture diagrams.
- Operators gain muscle memory before real incidents.
- The repository can distinguish "designed for failover" from "recently proven to fail over."

**Negative / Trade-offs**

- Rehearsals consume capacity and introduce controlled risk.
- Some services will need carefully scoped preview or standby targets before rehearsals are safe enough to automate.
- Freshness windows add operational work that must be budgeted.

## Boundaries

- This ADR sets the rehearsal requirement; it does not mandate a single cadence for every service.
- Services without declared redundancy are not forced into artificial failover drills.

## Related ADRs

- ADR 0098: Postgres high availability and automated failover
- ADR 0099: Automated backup restore verification
- ADR 0100: Formal RTO/RPO targets and disaster recovery playbook
- ADR 0171: Controlled fault injection for resilience validation
- ADR 0179: Service redundancy tier matrix
