# ADR 0218: Relational Database Replication And Single-Writer Policy

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ADR 0098 gave PostgreSQL an HA direction inside one environment, but the
broader platform needs a relational-data rule that also covers staging and
future database engines.

Relational systems are especially sensitive to hidden coupling:

- applications quietly connect to whichever node happens to answer
- replica lag is ignored until a failover or restore test
- staging is tempted to reuse the production cluster for convenience
- schema and migration practices blur between rehearsal and authority

## Decision

We will use a **single-writer, environment-local HA** policy for relational
databases.

### Writer rule

- Each relational domain has exactly one authoritative writer per environment.
- Production write traffic must terminate inside the production cell.
- Staging write traffic must terminate inside the staging cell.

### Intra-environment HA

Inside one environment cell, relational HA may use physical streaming,
consensus-managed leader election, or another engine-appropriate single-writer
replication strategy.

Cross-environment synchronous writes are forbidden. Production availability must
not depend on staging latency or staging health.

### Production to staging replication

Staging relational data must come from one of:

- sanitized snapshots
- logical subset replication
- bounded event replay into a staging-owned cluster

Staging must not be a promoted production replica. It is a separately owned
cluster with imported data, not part of the production failover set.

### Endpoint contract

Every relational service should declare:

- `rw_endpoint`: writer traffic only
- `ro_endpoint`: optional read-only traffic
- `admin_endpoint`: migration, backup, and operator control surface

Applications must not hard-code node IPs or infer write authority from DNS
accidents.

## Consequences

**Positive**

- Relational failover stays local to the environment that owns the data.
- Staging becomes more realistic without joining the production blast radius.
- Read and write paths become explicit enough for automation and health checks.

**Negative / Trade-offs**

- Separate staging clusters cost more than shared development databases.
- Sanitized snapshot and logical export tooling will need to be maintained.

## Boundaries

- This ADR does not mandate a single relational product. PostgreSQL remains the
  current platform standard, but the policy also governs any future relational
  engine.
- This ADR does not replace service-specific sizing, tuning, or schema
  ownership.

## Related ADRs

- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0098: Postgres high availability and automated failover
- ADR 0179: Service redundancy tier matrix
- ADR 0184: Failure-domain labels and anti-affinity policy
- ADR 0217: One-way environment data flow and replication authority
