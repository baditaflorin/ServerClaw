# ADR 0222: Failover Authority And Service Endpoint Separation

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Replicas only help when clients and operators know which endpoint is for which
purpose and who is allowed to promote a replica.

The platform currently has pieces of this pattern, such as VIP-based access for
PostgreSQL, but it still lacks one cross-service contract. Without it:

- applications keep embedding node-specific addresses
- health checks test the wrong role
- failover authority drifts into ad hoc scripts
- staging replicas start to look suspiciously like production standbys

## Decision

Every replicated service must declare both **failover authority** and
**endpoint separation**.

### Required endpoint types

- `write_endpoint`: only the current writer or leader
- `read_endpoint`: optional read-only traffic surface
- `management_endpoint`: operator and automation control surface
- `bootstrap_endpoint`: optional seeding or restore-only surface

### Authority rules

- Only the control plane of the owning environment may promote a writer.
- Staging components are never part of the production failover electorate.
- Automated failback is forbidden unless a service-specific ADR explicitly says
  otherwise.
- Clients must connect through the declared endpoint role, not through a node
  hostname that happens to work today.

### Health and routing rules

- Health probes must validate the expected role of the endpoint they are testing.
- Traffic-switching mechanisms such as VIPs, DNS, or proxy routing must follow
  the promoted leader automatically when the service contract requires it.
- Operator tooling must distinguish "replica is healthy" from "replica is
  promotable".

## Consequences

**Positive**

- Replica promotion becomes more deterministic and auditable.
- Read and write traffic can be governed separately.
- Environment boundaries stay intact during incidents.

**Negative / Trade-offs**

- Services with ad hoc connection strings will need cleanup before they can
  claim compliance.
- Some current health checks may be revealed as too shallow.

## Boundaries

- This ADR does not select whether a service uses VIPs, DNS, proxy routing, or
  a control-plane registry for traffic steering.
- This ADR governs authority and endpoint semantics; it does not define a
  specific failover timer or algorithm.

## Related ADRs

- ADR 0064: Health probe contracts
- ADR 0098: Postgres high availability and automated failover
- ADR 0170: Platform-wide timeout hierarchy
- ADR 0179: Service redundancy tier matrix
- ADR 0218: Relational database replication and single-writer policy
