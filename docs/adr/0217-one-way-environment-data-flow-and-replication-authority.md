# ADR 0217: One-Way Environment Data Flow And Replication Authority

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ADR 0073 gives the platform a governed path for promoting code and
configuration, but it does not fully define the mutable data relationship
between production and staging.

Without an explicit rule, teams tend to drift toward unsafe shortcuts:

- sharing one database across both environments
- using staging as an accidental failover target for production
- allowing manual exports from staging back into production
- copying all data everywhere because the replication mechanism happened to make
  it easy

That undermines both HA honesty and environment isolation.

## Decision

We will enforce **one-way data authority** between environments.

### Authority model

- `production` is the authority for live mutable production data.
- `staging` is a validation environment and must never write upstream into
  production data stores.
- Promotion moves application code, configuration, and migration intent, not
  mutable business data.

### Allowed production to staging flows

Cross-environment data movement must be declared as one of these types:

- `synthetic_seed`: fully generated, non-production data
- `sanitized_snapshot`: masked snapshot exported from production
- `logical_subset`: filtered and approved subset replication
- `event_replay`: bounded replay of approved events into staging

### Forbidden patterns

- bidirectional database replication between production and staging
- staging members participating in production quorum or leader election
- treating staging as an automatic production failover target
- importing staging-mutated records back into production outside an explicit,
  reviewed business workflow

## Consequences

**Positive**

- Production remains the clear system of record.
- Staging can still be realistic without quietly becoming part of the production
  blast radius.
- Operators gain a stable vocabulary for how test data got there and what its
  guarantees are.

**Negative / Trade-offs**

- Staging realism now depends on explicit masking and export pipelines.
- Some categories of real-time shadowing become intentionally harder because
  safety wins over convenience.

## Boundaries

- This ADR governs authority and direction, not the per-data-class replication
  mechanism.
- Explicit business workflows that move approved records from non-production to
  production are still possible, but they are not treated as environment
  replication.

## Related ADRs

- ADR 0072: Staging and production environment topology
- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0135: Data governance and classification policy
- ADR 0181: Off-host witness and control metadata replication
- ADR 0189: Network impairment test matrix for staging and previews
