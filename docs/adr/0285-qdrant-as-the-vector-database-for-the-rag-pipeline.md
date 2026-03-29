# ADR 0285: Qdrant As The Vector Database For The RAG Pipeline

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform's RAG (Retrieval-Augmented Generation) pipeline uses Apache Tika
(ADR 0275) to extract text from documents. Extracted chunks must be embedded
into a vector space and stored so that similarity queries can retrieve the
most relevant chunks for a given prompt. At present there is no dedicated
vector store; embeddings are either discarded after a single query or written
to flat files, making incremental retrieval impossible.

A vector database must satisfy three requirements for the RAG use case:

1. **Ingest API** — accept embedding vectors and metadata payloads over HTTP
   or gRPC without requiring a GUI or proprietary client session
2. **Query API** — answer approximate nearest-neighbour queries with filter
   predicates over metadata fields via the same transport
3. **Collection management API** — create, resize, and delete collections
   programmatically so Windmill pipelines can provision namespaced indexes
   for different document corpora without manual GUI steps

Qdrant is a CPU-only, open-source vector database written in Rust. It exposes
a REST API with a full OpenAPI specification and an equivalent gRPC API. All
operations—collection creation, point upsert, search, payload filtering, and
index management—are available via these APIs. The embedded web UI is
read-only and diagnostic; no write operation requires the browser.

## Decision

We will deploy **Qdrant** as the vector database for the platform RAG pipeline
and any other workload requiring approximate nearest-neighbour search.

### Deployment rules

- Qdrant runs as a Docker Compose service on the docker-runtime VM using the
  official `qdrant/qdrant` image
- The service is internal-only; no public subdomain is issued. It is reachable
  at `qdrant:6333` (REST) and `qdrant:6334` (gRPC) within the Compose network
- Persistent storage (vectors and payloads) is stored on a named Docker volume
  included in the backup scope (ADR 0086)
- The Qdrant API key is stored in OpenBao (ADR 0077) and injected as an
  environment variable at container startup; unauthenticated access is
  disabled
- Qdrant snapshots are taken via the REST Snapshot API on the platform's
  standard backup schedule and stored in MinIO (ADR 0274)

### API-first operation rules

- Collection creation is performed exclusively via the Qdrant REST API
  (`PUT /collections/{collection_name}`); collections are never created
  through the browser UI
- Embedding upsert and search are performed via the REST or gRPC API; direct
  file injection into the data directory is prohibited
- Collection naming follows the convention `{corpus}-{model_slug}` (e.g.
  `platform-docs-nomic-embed-text`) so that collections are self-describing
  and pipelines can resolve the target collection name without configuration
  lookups
- Windmill scripts that write embeddings use the OpenBao-vended API key;
  the key is never committed to source or embedded in a Windmill resource
  literal
- The Qdrant OpenAPI schema is served at `/openapi/rest-api.json`; it is
  fetched during CI and diffed against the pinned version to detect breaking
  changes before image promotion

### Collection lifecycle rules

- each corpus (document set or knowledge domain) owns a separate collection;
  cross-corpus queries are executed by the application layer, not inside
  Qdrant
- when a corpus is retired, its collection is deleted via the DELETE
  collections API; the corresponding MinIO snapshots are retained for
  30 days before expiry
- vector dimension and distance metric are declared in the Ansible role
  `defaults/main.yml` collection manifest; they cannot be changed after
  collection creation without a full re-index

## Consequences

**Positive**

- The RAG pipeline gains a durable, queryable vector store; embeddings
  computed during document ingestion are available for all subsequent
  queries without re-computation.
- All pipeline steps (embed, upsert, query) are HTTP or gRPC calls with
  documented schemas; Windmill can wire them together without browser
  sessions.
- Qdrant's payload filters allow metadata-driven retrieval (e.g. "return
  only chunks from documents tagged `compliance`") without a separate
  keyword index.
- The Rust implementation has a small memory footprint relative to
  JVM-based alternatives; baseline RAM is proportional to the indexed
  vector count, not a fixed overhead.

**Negative / Trade-offs**

- Vector dimension is fixed at collection creation; changing the embedding
  model requires a full collection drop and re-index, which is a potentially
  hours-long operation for large corpora.
- Qdrant's disk-based HNSW index requires the Docker volume to be on fast
  storage; placing it on a network-backed volume with high latency will
  degrade query performance.

## Boundaries

- Qdrant stores and queries vectors; it does not perform embedding
  computation. Embedding models run in Ollama (ADR 0145) or an external
  inference endpoint.
- Qdrant does not replace Typesense (ADR 0277) for keyword full-text search;
  hybrid retrieval pipelines call both services and merge results in the
  application layer.
- The Qdrant web dashboard is available at port 6333 for diagnostic purposes
  only; write operations through the dashboard are treated as drift and
  reconciled on the next converge.
- Multi-node Qdrant clustering is not in scope; the deployment is single-node.

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0145: Ollama for local LLM inference
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline
- ADR 0277: Typesense as the full-text search engine for internal structured data

## References

- <https://qdrant.tech/documentation/interfaces/rest/>
- <https://qdrant.tech/documentation/interfaces/grpc/>
