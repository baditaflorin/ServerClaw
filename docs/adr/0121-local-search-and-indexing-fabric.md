# ADR 0121: Local Search and Indexing Fabric

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.111.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

ADR 0095 proposed a unified platform search that would index runbooks, ADRs, configs, and operational data. That ADR was primarily concerned with the operator-facing search experience. The platform now has additional search consumers that were not anticipated:

- The triage engine (ADR 0114) needs to search runbooks by symptom string to surface relevant remediation procedures.
- The case library (ADR 0118) needs full-text search over failure case records.
- The goal compiler (ADR 0112) needs to look up canonical action aliases and workflow IDs by natural-language name.
- The operator observation loop (ADR 0071) needs to search the command catalog (ADR 0048) and ADRs for relevant context before composing a recommendation.

All of these are local queries against platform-owned data. None of them require semantic similarity over arbitrary text. For a corpus of ~200 ADRs, ~80 runbooks, ~500 receipts, ~1000 case records, and ~10,000 log-summary events, BM25 full-text search with trigram matching and faceted metadata filtering is demonstrably sufficient.

Introducing a vector database and embedding pipeline for this corpus would add:
- a GPU or cloud API dependency for embedding generation
- an embedding refresh pipeline whenever source documents change
- infrastructure to host and query the vector index
- debugging complexity when retrieval quality degrades

All of this overhead for marginal improvement over BM25 on a structured, domain-specific corpus with consistent vocabulary.

## Decision

We will build a **local search and indexing fabric** entirely within Postgres, using `pg_trgm` (trigram matching) and the built-in `tsvector`/`tsquery` (BM25 full-text search). No vector database, no external search service, no embedding pipeline.

### Indexed collections

| Collection | Source | Update trigger | Primary search fields |
|---|---|---|---|
| ADRs | `docs/adr/*.md` | Git push hook | title, context, decision, consequences |
| Runbooks | `docs/runbooks/*.md` | Git push hook | title, body, commands |
| Receipts | Mutation ledger (ADR 0115) | Ledger event insert | workflow_id, actor, target, receipt summary |
| Failure cases | Case library (ADR 0118) | Case create/update | title, symptoms, root_cause, remediation_steps |
| Alerts | GlitchTip + alerting router | Alert fire event | alert name, service, message |
| Configs | `config/*.yaml`, `config/*.json` | Git push hook | file path, content |
| Command catalog | `config/workflow-catalog.json` | Git push hook | workflow ID, description, tags |
| Topology | World-state materializer (ADR 0113) | World-state refresh | node IDs, labels, metadata |
| Log summaries | Loki (ADR 0052) | Nightly batch | service, log level, message digest |

### Schema

```sql
CREATE TABLE search.documents (
    id              BIGSERIAL PRIMARY KEY,
    doc_id          TEXT NOT NULL,               -- stable external ID (e.g. 'adr:0112', 'runbook:configure-step-ca')
    collection      TEXT NOT NULL,               -- collection name from table above
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,               -- full text content for FTS
    url             TEXT,                        -- deep link for ops portal
    metadata        JSONB NOT NULL DEFAULT '{}', -- facets: service, tag, date, severity, ...
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash    TEXT NOT NULL,               -- SHA256 of body; used to skip re-indexing unchanged docs
    search_vector   TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', body),  'B')
    ) STORED
);

CREATE INDEX search_documents_fts_idx  ON search.documents USING GIN (search_vector);
CREATE INDEX search_documents_trgm_idx ON search.documents USING GIN (title gin_trgm_ops);
CREATE INDEX search_documents_coll_idx ON search.documents (collection);
CREATE INDEX search_documents_meta_idx ON search.documents USING GIN (metadata);
UNIQUE INDEX search_documents_docid_idx ON search.documents (doc_id, collection);
```

### Query API

```python
# platform/search/client.py

search = SearchClient()

# Full-text search across all collections
results = search.query("netbox deployment failed connection pool")

# Search within a collection with facets
results = search.query(
    "certificate expiry renewal",
    collection="runbooks",
    facets={"service": "step-ca"},
    limit=5,
)

# Trigram prefix search (for autocomplete in the ops portal and CLI)
results = search.suggest("converge-net", collection="command_catalog")

# Structured metadata filter (no text query needed)
results = search.filter(collection="failure_cases", facets={"root_cause_category": "deployment_regression"})
```

### Query execution

Queries combine FTS rank and trigram similarity into a single composite score:

```sql
SELECT
    doc_id,
    collection,
    title,
    url,
    metadata,
    ts_rank_cd(search_vector, query) * 0.7 +
    similarity(title, :raw_query)    * 0.3  AS score
FROM search.documents,
     plainto_tsquery('english', :raw_query) AS query
WHERE search_vector @@ query
   OR title % :raw_query                    -- trigram fallback for typos / short terms
ORDER BY score DESC
LIMIT :limit;
```

This query handles both exact-term FTS matches and fuzzy title matches in a single pass.

### Indexer

A Windmill workflow `rebuild-search-index` runs on every git push (via a webhook from the Gitea or bare git repo) and nightly:

```
1. Walk docs/adr/, docs/runbooks/, config/ — hash each file
2. For files whose hash has changed since last index: re-parse and upsert into search.documents
3. For collections backed by Postgres (receipts, cases, alerts): upsert any rows added since last indexer run
4. Post indexer stats to mutation ledger (ADR 0115) and Mattermost
```

### Platform CLI integration

```bash
$ lv3 search "postgres connection pool"
[runbook] handle-postgres-connection-exhaustion       0.91  docs/runbooks/
[case]    netbox-connection-pool-saturation-2026-03  0.87  cases/
[adr]     ADR 0098: Postgres High Availability        0.72  docs/adr/
[alert]   postgres_connection_count_high              0.61  alerts/

$ lv3 search "converge" --collection command_catalog
[cmd]  converge-netbox     deploy or converge the NetBox service
[cmd]  converge-step-ca    converge the step-ca certificate authority
[cmd]  converge-keycloak   converge the Keycloak SSO service
```

### Ops portal integration

The search bar in the ops portal (ADR 0093) calls `GET /v1/search?q=<query>&collection=<optional>` on the platform API gateway (ADR 0092), which proxies to the search client. Results are displayed with collection-specific icons and deep links.

### Coverage limitations and future extension

BM25 is known to under-perform for paraphrase retrieval: a user who searches "cert is about to expire" may not retrieve the runbook titled "TLS certificate renewal procedure" because no common terms are shared. This gap is addressed by:

1. Ensuring all runbooks and cases have explicit `tags` in their frontmatter that use canonical platform vocabulary.
2. Adding a synonym table in `config/search-synonyms.yaml` that expands common operator shorthands before query execution.
3. Accepting that ~10–20% of searches may need a reformulation; this is tolerable for an operator audience that knows the platform vocabulary.

Vector search is explicitly deferred. If the synonym table approach proves insufficient after 60 days of use, the indexing fabric schema is designed to accommodate an additional `embedding` column without restructuring.

## Consequences

**Positive**

- All platform knowledge — ADRs, runbooks, cases, configs, topology, command catalog — is accessible via a single `lv3 search` command and a single API endpoint.
- No external infrastructure dependencies. The search fabric is entirely within the existing Postgres instance.
- Adding a new indexed collection requires only a new indexer function and a `collection` type constant; no schema migration is needed.
- The triage engine, case library, and goal compiler all share the same search infrastructure rather than maintaining separate lookup logic.

**Negative / Trade-offs**

- BM25 does not handle semantic paraphrase. Synonym table maintenance is an ongoing editorial task.
- The nightly batch indexer means log summaries and alert documents are up to 24 hours stale. Real-time alert search is better served by direct GlitchTip queries.
- Trigram indexes on large text bodies are memory-intensive. The `body` column should store summaries (first 2000 characters) rather than full document content for large ADRs and runbooks.

## Boundaries

- This ADR covers indexing and retrieval of platform-owned, text-format operational data. It does not index binary artefacts, container images, or backup archives.
- There is no embedding pipeline, no vector database, and no LLM in the retrieval path.
- Search quality improvements via synonym tables are config changes. Search quality improvements via vector embeddings require a separate future ADR.

## Related ADRs

- ADR 0048: Command catalog (indexed collection)
- ADR 0052: Loki logs (log summary source for nightly batch)
- ADR 0061: GlitchTip (alert documents indexed)
- ADR 0090: Platform CLI (`lv3 search` command)
- ADR 0092: Unified platform API gateway (`/v1/search` endpoint)
- ADR 0093: Interactive ops portal (search bar consumer)
- ADR 0095: Unified platform search (original proposal; this ADR supersedes and implements it)
- ADR 0098: Postgres HA (underlying storage for search schema)
- ADR 0112: Deterministic goal compiler (queries command catalog via search for alias resolution)
- ADR 0114: Rule-based incident triage engine (queries runbooks via search for discriminating check steps)
- ADR 0115: Event-sourced mutation ledger (receipt documents indexed)
- ADR 0118: Replayable failure case library (case documents indexed and searched from triage)
