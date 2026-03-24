# Workstream ADR 0121: Local Search and Indexing Fabric

- ADR: [ADR 0121](../adr/0121-local-search-and-indexing-fabric.md)
- Title: Postgres-native BM25 + trigram search over ADRs, runbooks, receipts, cases, alerts, configs, command catalog, and topology — no vector DB, no embeddings, no external service
- Status: merged
- Branch: `codex/adr-0121-local-search-indexing-fabric`
- Worktree: `.worktrees/adr-0121`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0052-loki-logs`, `adr-0061-glitchtip`, `adr-0090-platform-cli`, `adr-0092-platform-api-gateway`, `adr-0093-interactive-ops-portal`, `adr-0095-unified-platform-search`, `adr-0098-postgres-ha`, `adr-0113-world-state-materializer`, `adr-0115-mutation-ledger`, `adr-0118-failure-case-library`
- Conflicts With: none
- Shared Surfaces: `scripts/search_fabric/`, `search.documents` Postgres schema, `config/search-synonyms.yaml`, `/v1/search` API gateway endpoint, `lv3 search` CLI command

## Scope

- create Postgres migration `migrations/0014_search_schema.sql` — `search.documents` table with generated `tsvector` column, GIN FTS index, `pg_trgm` trigram index, metadata GIN index, and unique constraint on `(doc_id, collection)` from ADR 0121; `CREATE EXTENSION IF NOT EXISTS pg_trgm;`
- create `scripts/search_fabric/__init__.py`
- create `scripts/search_fabric/client.py` — `SearchClient.query()`, `SearchClient.suggest()`, `SearchClient.filter()` with a repo-testable BM25 + trigram implementation that mirrors the ADR 0121 retrieval contract while the SQL migration remains ready for live Postgres use
- create `scripts/search_fabric/indexer.py` — `SearchIndexer.upsert_document()`, `SearchIndexer.index_collection()`, `SearchIndexer.index_all()` — handles content-hash deduplication, collection routing, and writes `build/search-index/documents.json`
- create `scripts/search_fabric/collectors/` directory with one module per collection:
  - `adr_collector.py` — walks `docs/adr/*.md`, parses frontmatter and body
  - `runbook_collector.py` — walks `docs/runbooks/*.md`
  - `catalog_collector.py` — reads `config/command-catalog.json` plus `config/workflow-catalog.json`
  - `config_collector.py` — walks `config/*.yaml` and `config/*.json`
  - `receipt_collector.py` — indexes repo receipts under `receipts/**/*.json`
  - `case_collector.py` — reads `cases/` or `receipts/failure-cases/` when present
  - `alert_collector.py` — indexes alert receipts when present and otherwise falls back to managed alert rules
  - `topology_collector.py` — materializes node search documents from `config/dependency-graph.json`
- create `config/search-synonyms.yaml` — initial synonym table (cert → certificate, rotate → rotation → credential refresh, converge → deploy → apply → idempotent run, etc.)
- create `config/windmill/scripts/rebuild-search-index.py` — Windmill workflow helper: runs `SearchIndexer.index_all()` and emits index stats as JSON
- register `/v1/search` route on the platform API gateway (ADR 0092): `GET /v1/search?q=<query>&collection=<optional>&limit=<optional>`
- add `lv3 search <query>` command to the platform CLI (ADR 0090)
- add search bar to the ops portal (ADR 0093): calls `/v1/search`; renders results with collection icons and deep links
- write `tests/test_search_fabric.py` — test BM25 ranking, trigram fallback, synonym expansion, empty-corpus edge case, collection filter

## Non-Goals

- Vector embeddings or semantic similarity
- Indexing binary artefacts, container images, or backup archives
- Real-time log streaming search — that is Loki's job

## Expected Repo Surfaces

- `migrations/0014_search_schema.sql`
- `scripts/search_fabric/__init__.py`
- `scripts/search_fabric/client.py`
- `scripts/search_fabric/indexer.py`
- `scripts/search_fabric/collectors/` (8 collector modules)
- `config/search-synonyms.yaml`
- `config/windmill/scripts/rebuild-search-index.py`
- `docs/runbooks/search-indexing-fabric.md`
- `docs/adr/0121-local-search-and-indexing-fabric.md`
- `docs/workstreams/adr-0121-search-indexing-fabric.md`

## Expected Live Surfaces

- `search.documents` contains rows for all current ADRs and runbooks after the first indexer run
- `lv3 search "certificate renewal"` returns at least one runbook and one ADR
- `lv3 search "converge netbox"` returns the `converge-netbox` command catalog entry (via synonym expansion)
- `/v1/search?q=postgres+connection+pool` returns case and runbook results via the API gateway
- The ops portal search bar returns results within 300ms for a typical query

## Verification

- Run `uv run --with pytest --with pyyaml --with fastapi --with httpx --with cryptography --with jinja2 --with itsdangerous --with python-multipart python -m pytest tests/test_search_fabric.py tests/test_lv3_cli.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py -q` → all tests pass
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
- Nightly rebuild placeholder seeded in Windmill defaults

## Notes For The Next Assistant

- `pg_trgm` must be enabled on the Postgres database before the migration runs: `CREATE EXTENSION IF NOT EXISTS pg_trgm;`. Include this in the migration file but also document it in the runbook since it requires superuser on some Postgres configs.
- The `body` column should store at most 2000 characters per document (truncate with a `...` suffix for longer documents). Storing full ADR bodies in the trigram index will cause the GIN index to grow very large; summaries are sufficient for BM25 ranking.
- The synonym expansion should be applied to the query string before calling `plainto_tsquery()`. Implement it as a simple string replacement from the synonyms YAML rather than using Postgres `thesaurus` dictionaries (simpler to maintain and debug).
- The git push webhook trigger for the indexer rebuild requires a webhook secret configured in the repo server. Use `config/controller-local-secrets.json` to store the webhook secret; document the registration step in the indexer runbook.
