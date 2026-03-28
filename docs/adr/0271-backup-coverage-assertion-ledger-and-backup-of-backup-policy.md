# ADR 0271: Backup Coverage Assertion Ledger And Backup-Of-Backup Policy

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Restore verification exposed a severe class of failure that normal backup
dashboards often hide: one protected guest had no PBS backup available at all.
That is a coverage failure, not a restore mechanics failure.

The platform also needs explicit policy for protecting the backup service and
its metadata, not just the guests it stores.

## Decision

We will maintain a **backup coverage assertion ledger** and a declared
**backup-of-backup policy**.

### Coverage ledger fields

- protected asset identity
- expected backup cadence and retention tier
- last successful backup evidence
- last verified restore evidence
- coverage state: protected, degraded, or uncovered

### Policy rules

- any protected asset without fresh backup evidence is a policy failure
- the backup service itself must have an independent recovery path
- release and readiness surfaces must show uncovered assets explicitly

## Consequences

**Positive**

- missing backups become visible before restore drills fail
- operators can distinguish coverage gaps from restore defects
- backup infrastructure receives the same rigor as application workloads

**Negative / Trade-offs**

- the ledger adds one more truth surface to keep current
- backup-of-backup strategy may require extra storage and operational handling

## Boundaries

- This ADR governs backup coverage and evidence policy.
- It does not define the restore warm-up model for specific services.

## Related ADRs

- ADR 0020: Initial storage and backup model
- ADR 0029: Dedicated backup VM with local PBS
- ADR 0051: Control-plane backup recovery and break-glass
- ADR 0099: Automated backup restore verification
- ADR 0100: RTO, RPO, and disaster recovery playbook
