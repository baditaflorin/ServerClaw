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
