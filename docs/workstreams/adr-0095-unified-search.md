# Workstream ADR 0095: Unified Search Across Platform Services

- ADR: [ADR 0095](../adr/0095-unified-platform-search.md)
- Title: Zinc Search indexing audit log, topology, ADRs, and catalogs; exposed at /v1/platform/search via the API gateway
- Status: ready
- Branch: `codex/adr-0095-unified-search`
- Worktree: `../proxmox_florin_server-unified-search`
- Owner: codex
- Depends On: `adr-0092-platform-api-gateway`, `adr-0054-netbox`, `adr-0066-audit-log`, `adr-0069-agent-tool-registry`, `adr-0070-rag-context`
- Conflicts With: none
- Shared Surfaces: `config/agent-tool-registry.json`, `config/api-gateway-catalog.json`, Compose stack on `docker-runtime-lv3`

## Scope

- write `scripts/search_index_catalog.py` — indexes service and subdomain catalogs into Zinc
- write `scripts/search_index_adrs.py` — indexes all ADR documents into Zinc
- write `scripts/search_index_audit.py` — indexes mutation audit log entries into Zinc (15-min schedule)
- write `scripts/search_index_netbox.py` — indexes NetBox VMs and IPs into Zinc (hourly schedule)
- write `scripts/search_index_windmill.py` — indexes Windmill run history into Zinc (15-min schedule)
- write Ansible role `zinc_search_runtime` — deploys Zinc Search Compose service on `docker-runtime-lv3`
- add `/v1/platform/search` endpoint to the API gateway (FastAPI route in `scripts/api_gateway/main.py`)
- add `platform_search` tool to `config/agent-tool-registry.json`
- schedule all indexer scripts in Windmill (5 new scheduled flows)
- add `lv3 search "<query>"` command to the platform CLI (ADR 0090 integration)
- add health probe for Zinc to `config/health-probe-catalog.json`

## Non-Goals

- Indexing Loki logs in Zinc (Loki has its own query API; the search endpoint passes log queries through)
- Full-text search within Mattermost messages (Mattermost has built-in search; cross-service correlation is the priority)
- Real-time indexing (schedule-based indexing is sufficient)

## Expected Repo Surfaces

- `scripts/search_index_catalog.py`
- `scripts/search_index_adrs.py`
- `scripts/search_index_audit.py`
- `scripts/search_index_netbox.py`
- `scripts/search_index_windmill.py`
- `roles/zinc_search_runtime/`
- `config/agent-tool-registry.json` (patched: `platform_search` tool added)
- `config/api-gateway-catalog.json` (patched: search route added)
- `config/health-probe-catalog.json` (patched: zinc probe added)
- `docs/adr/0095-unified-platform-search.md`
- `docs/workstreams/adr-0095-unified-search.md`

## Expected Live Surfaces

- Zinc Search accessible on `docker-runtime-lv3:4080` (internal only)
- `GET /v1/platform/search?q=postgres` returns results from at least 3 sources
- `lv3 search postgres` returns results in the terminal
- All 5 indexer Windmill flows have at least one successful run

## Verification

- `lv3 search keycloak` returns at least: one ADR result, one topology result, one audit result
- `GET /v1/platform/search?q=keycloak&sources=adrs` returns only ADR results
- Zinc index `platform-audit` has entries within 15 minutes of a test audit log entry being written
- Agent tool `platform_search` call returns correctly structured results (test via the agent tool registry test harness)

## Merge Criteria

- All 5 indexers have run successfully against the live platform
- `/v1/platform/search?q=postgres` returns results
- `lv3 search postgres` command works
- Zinc health probe passes

## Notes For The Next Assistant

- Zinc's default index mapping does not handle date fields well; explicitly map `timestamp` as a `date` field when creating indexes via the Zinc API to enable time-range filtering
- The audit log indexer must handle the case where the audit log is a large file; use `since_last_run` checkpoint in `receipts/search-checkpoints/<index>.json` to avoid re-indexing the entire log every 15 minutes
- Zinc Search runs on port 4080 by default; this conflicts with nothing, but verify before deploying
- The `/v1/platform/search` gateway route must forward the caller's Keycloak token to enforce access control; Zinc itself has basic auth; the gateway translates the JWT to Zinc credentials stored in OpenBao
