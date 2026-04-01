# ADR 0277: Typesense As The Full-Text Search Engine For Internal Structured Data

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.125
- Implemented In Platform Version: 0.130.80
- Implemented On: 2026-03-31
- Date: 2026-03-29

## Context

The platform has two search facilities today:

- **SearXNG** (ADR 0148) answers external web meta-search queries; it does
  not index internal data
- **Qdrant** (ADR 0198 / ADR 0263) answers semantic vector queries over
  embedded document corpora

Neither answers fast, typo-tolerant, keyword-exact queries over structured
internal records such as:

- the platform service catalog entries
- NetBox network objects (hosts, IP ranges, devices)
- Outline knowledge base articles
- Gitea repository and issue titles
- Windmill script and workflow identifiers
- Grist operational tables (ADR 0279)

Operators today find records by navigating each service's own UI or by running
ad-hoc queries against PostgreSQL. There is no unified keyword-search entry
point for internal data, and the existing search fabric (ADR 0121) is
Postgres-backed full-text which does not offer typo tolerance, instant-search
ranking, or faceted filtering.

Typesense is a CPU-only, open-source search engine that stores RAM-indexed
collections, handles typos, and responds in single-digit milliseconds. Its RAM
footprint scales with indexed collection size, not query load.

## Decision

We will deploy **Typesense** as the full-text search engine for internal
structured platform data.

### Deployment rules

- Typesense runs as a Docker Compose service on the docker-runtime VM
- A single-node deployment is used; clustering is deferred
- The API key is stored in OpenBao and injected at service start following
  ADR 0077
- The data volume is a named Docker volume; it is included in the backup scope
  (ADR 0086)

### Collection ownership

- each consumer owns and manages its own Typesense collection
- collection schemas are declared in the consumer service's Ansible role
- the platform catalog collection (`platform-services`) is managed by the
  `api_gateway_runtime` role and updated on every converge
- Outline, Gitea, and NetBox populate their collections via
  index-sync scripts or Windmill workflows on a scheduled basis

### Query contract

- Typesense answers keyword, prefix, and faceted queries over structured records
- Qdrant answers semantic embedding queries over text corpora
- SearXNG answers external web search queries
- each layer is invoked for the query class it is best suited to; no single
  search call is expected to span all three

## Consequences

**Positive**

- Operators get a unified, typo-tolerant keyword search across all platform
  services without touching each service's individual UI.
- Collection schemas are explicit and versioned in the Ansible roles, making
  index shape auditable.
- Typesense's instant-search API suits autocomplete and live-filter UIs
  without query rate concerns.
- The separation between Typesense (keyword) and Qdrant (semantic) keeps each
  index optimised for its actual query pattern.

**Negative / Trade-offs**

- Each consumer must implement an index-sync pipeline; there is no universal
  connector that automatically mirrors records from every data source.
- In-memory indexes are lost on restart and must be rebuilt from source; the
  build time is bounded by collection size but must be accounted for in
  restart SLOs.

## Boundaries

- Typesense does not replace Qdrant for embedding-backed semantic retrieval.
- Typesense does not replace SearXNG for external web search.
- Typesense does not index log lines, metrics, or trace spans; those remain
  in Loki, InfluxDB, and Tempo.
- Typesense is not used as a primary database; source-of-truth records live in
  PostgreSQL, and Typesense holds derived search indexes only.

## Related ADRs

- ADR 0046: NetBox for network documentation
- ADR 0121: Local search and indexing fabric
- ADR 0148: SearXNG for private web search
- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0199: Outline as the living knowledge wiki
- ADR 0263: Qdrant, PostgreSQL, and local search as the ServerClaw memory
  substrate

## References

- <https://typesense.org/docs/>
