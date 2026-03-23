# Workstream ADR 0121: Local Search and Indexing Fabric

- ADR: [ADR 0121](../adr/0121-local-search-and-indexing-fabric.md)
- Title: Postgres-native BM25 + trigram search over ADRs, runbooks, receipts, cases, alerts, configs, command catalog, and topology — no vector DB, no embeddings, no external service
- Status: ready
- Branch: `codex/adr-0121-search-fabric`
- Worktree: `../proxmox_florin_server-search-fabric`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0052-loki-logs`, `adr-0061-glitchtip`, `adr-0090-platform-cli`, `adr-0092-platform-api-gateway`, `adr-0093-interactive-ops-portal`, `adr-0095-unified-platform-search`, `adr-0098-postgres-ha`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0118-failure-case-library`
- Conflicts With: none
- Shared Surfaces: `platform/search/`, `search.documents` Postgres schema, `config/search-synonyms.yaml`, `/v1/search` API gateway endpoint, `lv3 search` CLI command

## Scope

- create Postgres migration `migrations/0014_search_schema.sql` — `search.documents` table with generated `tsvector` column, GIN FTS index, `pg_trgm` trigram index, metadata GIN index, and unique constraint on `(doc_id, collection)` from ADR 0121; `CREATE EXTENSION IF NOT EXISTS pg_trgm;`
- create `platform/search/__init__.py`
- create `platform/search/client.py` — `SearchClient.query()`, `SearchClient.suggest()`, `SearchClient.filter()` with the composite BM25 + trigram SQL query from ADR 0121
- create `platform/search/indexer.py` — `Indexer.upsert_document()`, `Indexer.index_collection()`, `Indexer.index_all()` — handles content-hash deduplication, collection routing
- create `platform/search/collectors/` directory with one module per collection:
  - `adr_collector.py` — walks `docs/adr/*.md`, parses frontmatter and body
  - `runbook_collector.py` — walks `docs/runbooks/*.md`
  - `catalog_collector.py` — reads `config/workflow-catalog.json` entries
  - `config_collector.py` — walks `config/*.yaml` and `config/*.json`
  - `receipt_collector.py` — queries `ledger.events` for recent receipts
  - `case_collector.py` — queries `cases.failure_cases` for resolved cases
  - `alert_collector.py` — queries GlitchTip API for recent alerts
  - `topology_collector.py` — queries `world_state.current_view` for the NetBox topology snapshot
- create `config/search-synonyms.yaml` — initial synonym table (cert → certificate, rotate → rotation → credential refresh, converge → deploy → apply → idempotent run, etc.)
- create `windmill/search/rebuild-search-index.py` — Windmill workflow: runs `Indexer.index_all()`; posts index stats to Mattermost; scheduled nightly and triggered on git push webhook
- register `/v1/search` route on the platform API gateway (ADR 0092): `GET /v1/search?q=<query>&collection=<optional>&limit=<optional>`
- add `lv3 search <query>` command to the platform CLI (ADR 0090)
- add search bar to the ops portal (ADR 0093): calls `/v1/search`; renders results with collection icons and deep links
- write `tests/unit/test_search_client.py` — test BM25 ranking, trigram fallback, synonym expansion, empty-corpus edge case, collection filter

## Non-Goals

- Vector embeddings or semantic similarity
- Indexing binary artefacts, container images, or backup archives
- Real-time log streaming search — that is Loki's job

## Expected Repo Surfaces

- `migrations/0014_search_schema.sql`
- `platform/search/__init__.py`
- `platform/search/client.py`
- `platform/search/indexer.py`
- `platform/search/collectors/` (8 collector modules)
- `config/search-synonyms.yaml`
- `windmill/search/rebuild-search-index.py`
- `docs/adr/0121-local-search-and-indexing-fabric.md`
- `docs/workstreams/adr-0121-search-indexing-fabric.md`

## Expected Live Surfaces

- `search.documents` contains rows for all current ADRs and runbooks after the first indexer run
- `lv3 search "certificate renewal"` returns at least one runbook and one ADR
- `lv3 search "converge netbox"` returns the `converge-netbox` command catalog entry (via synonym expansion)
- `/v1/search?q=postgres+connection+pool` returns case and runbook results via the API gateway
- The ops portal search bar returns results within 300ms for a typical query

## Verification

- Run `pytest tests/unit/test_search_client.py -v` → all tests pass
- Run the `rebuild-search-index` workflow manually → confirm index stats (doc counts per collection) are posted to Mattermost
- Run `lv3 search "tls cert expires"` → confirm at least one certificate-related ADR or runbook appears in results
- Run `lv3 search "converge"` → confirm command catalog entries appear
- Run `lv3 search "xyzzy foobar notaword"` → confirm graceful empty result, not a 500 error

## Merge Criteria

- Unit tests pass including empty-corpus and synonym-expansion tests
- All 8 collectors producing documents after a full index run
- `lv3 search` command working on the controller
- `/v1/search` API endpoint tested via the gateway
- Search bar rendered in the ops portal
- Nightly rebuild scheduled in Windmill

## Notes For The Next Assistant

- `pg_trgm` must be enabled on the Postgres database before the migration runs: `CREATE EXTENSION IF NOT EXISTS pg_trgm;`. Include this in the migration file but also document it in the runbook since it requires superuser on some Postgres configs.
- The `body` column should store at most 2000 characters per document (truncate with a `...` suffix for longer documents). Storing full ADR bodies in the trigram index will cause the GIN index to grow very large; summaries are sufficient for BM25 ranking.
- The synonym expansion should be applied to the query string before calling `plainto_tsquery()`. Implement it as a simple string replacement from the synonyms YAML rather than using Postgres `thesaurus` dictionaries (simpler to maintain and debug).
- The git push webhook trigger for the indexer rebuild requires a webhook secret configured in the repo server. Use `config/controller-local-secrets.json` to store the webhook secret; document the registration step in the indexer runbook.
