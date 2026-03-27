# Search Indexing Fabric

## Purpose

This runbook covers ADR 0121's local search and indexing fabric for ADRs, runbooks, receipts, command catalog entries, configs, alerts, topology, and failure cases.

## Repo Surfaces

- `scripts/search_fabric/`
- `config/search-synonyms.yaml`
- `config/windmill/scripts/rebuild-search-index.py`
- `build/search-index/documents.json`
- `migrations/0014_search_schema.sql`

## Preconditions

1. Run from a checkout that has the latest `main` content.
2. Ensure `config/search-synonyms.yaml` reflects the current platform vocabulary before rebuilding after a major naming change.
3. If applying the Postgres schema live, connect as a role that can create `pg_trgm`.

## Rebuild The Repo Index

Run the repo-managed rebuild helper:

```bash
python3 config/windmill/scripts/rebuild-search-index.py --repo-path /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
```

This writes `build/search-index/documents.json` and prints collection counts, updated rows, and skipped rows.

## Query The Index

Use the platform CLI locally:

```bash
lv3 search "certificate renewal"
lv3 search "converge netbox" --collection command_catalog
```

## Apply The Postgres Schema

When the search fabric is promoted from repo-only use to the shared PostgreSQL instance, apply:

```bash
psql "$SEARCH_DATABASE_DSN" -f migrations/0014_search_schema.sql
```

If the database policy blocks extension creation for the application role, install `pg_trgm` once as a superuser first, then rerun the migration.

## Windmill Registration Notes

- Seed `config/windmill/scripts/rebuild-search-index.py` through the managed Windmill runtime role.
- Store the git-push webhook secret in the controller-local manifest before enabling an automatic webhook trigger.
- Keep the nightly schedule disabled until the script is applied live from `main`.

## Verification

1. `pytest tests/test_search_fabric.py tests/test_lv3_cli.py tests/test_api_gateway.py tests/test_interactive_ops_portal.py -q`
2. `python3 config/windmill/scripts/rebuild-search-index.py`
3. `lv3 search "tls cert expires"`
4. `lv3 search "converge" --collection command_catalog`

## Live Apply Notes

- The API gateway runtime must stage both `docs/` and `receipts/` into `/opt/api-gateway/service` and copy them into the image so `/v1/search` can index runbooks and receipts in-container.
- The Windmill worker checkout must stage `docs/`, `receipts/`, and `scripts/search_fabric/` from `{{ playbook_dir }}/..` so the mounted repo under `/srv/proxmox_florin_server` matches the current repository workspace.
- `scripts/search_fabric/utils.py` now treats non-UTF8 text as replace-on-read and treats malformed JSON as a skipped document by returning the collector default payload.
- `scripts/search_fabric/collectors/receipt_collector.py` skips empty payloads so malformed receipt JSON does not produce placeholder documents in the live index.
- The 2026-03-26 live apply hit unrelated runtime drift in the Windmill `uv` permission task and a transient SSH reconnect during the API gateway replay. The final recovery used the repo-managed file layout plus a documented manual sync of the corrected search-fabric files into `/opt/api-gateway/service` and `/srv/proxmox_florin_server`, followed by `docker compose build api-gateway && docker compose up -d api-gateway` and a checkout ownership repair for `/srv/proxmox_florin_server/build`.
- End-to-end verification for the 2026-03-26 live apply:
  - `curl -H "Authorization: Bearer $(cat .local/platform-context/api-token.txt)" "https://api.lv3.org/v1/search?q=certificate%20renewal&collection=runbooks&limit=5"`
  - `curl -H "Authorization: Bearer $(cat .local/platform-context/api-token.txt)" "https://api.lv3.org/v1/search?q=converge%20netbox&collection=command_catalog&limit=5"`
  - `python3 /srv/proxmox_florin_server/config/windmill/scripts/rebuild-search-index.py --repo-path /srv/proxmox_florin_server`
