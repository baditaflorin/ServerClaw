# ADR 0219: Data-Class Replication Policies For Queues, Object Stores, Search, Cache, Secrets, And Time-Series

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Not every stateful system behaves like a relational database. The platform will
continue to accumulate multiple state classes:

- queues and event streams
- object or blob stores
- search and vector indexes
- caches and sessions
- secret or key-value authorities
- metrics, logs, traces, and other time-series stores

Using one replication story for all of them would create the wrong guarantees
for at least half of them.

## Decision

We will govern replication by **data class** rather than by product name alone.

### Queue and stream systems

- Intra-environment replication protects availability inside one cell.
- Cross-environment movement uses bounded export or replay, not shared consumer
  groups across production and staging.
- Staging consumers must never commit offsets back into production authorities.

### Object and blob stores

- Versioned replication may copy approved prefixes from production to recovery
  or staging stores.
- Staging writes remain isolated to staging-owned buckets or prefixes.
- Object storage is not treated as a general-purpose bidirectional sync surface.

### Search and vector indexes

- Search and vector stores are derived state unless an explicit ADR says
  otherwise.
- They should rebuild from canonical upstream data instead of being treated as
  the primary source of truth.
- Cross-environment replication is optional and should prefer re-indexing from
  approved seed data.

### Cache and session stores

- Cache, session, and ephemeral coordination stores are environment-local only.
- They are rebuilt or repopulated, not cross-replicated between production and
  staging.

### Secrets and key-value authorities

- Each environment gets its own authority and sealing boundary.
- Only narrow bootstrap trust anchors may be exported across environments.
- Whole-authority replication from production into staging is forbidden.

### Time-series and observability stores

- Observability systems may forward or downsample selected production telemetry
  into a central or staging-visible analysis surface.
- Staging observability data must not drive production control decisions.

## Consequences

**Positive**

- Different database and state types get guarantees aligned with their real
  behavior.
- Rebuildable systems stop consuming the same operational rigor as primary
  authorities.
- Environment isolation improves without losing realistic test and replay paths.

**Negative / Trade-offs**

- Operators must understand more than one replication mode.
- Platform catalogs will need enough metadata to express these classes cleanly.

## Boundaries

- This ADR governs replication posture by state class; it does not select a
  vendor or deploy a specific product.
- If a future service wants a class-specific exception, it needs its own ADR
  rather than silently redefining the class.

## Related ADRs

- ADR 0098: Postgres high availability and automated failover
- ADR 0113: World-state materializer
- ADR 0148: Private web search live on production
- ADR 0198: Qdrant vector search semantic RAG
- ADR 0217: One-way environment data flow and replication authority
