# Service Dependency Graph Runtime

## Purpose

ADR 0117 promotes the platform dependency graph from the static `config/dependency-graph.json` report into a queryable runtime persisted in `graph.nodes` and `graph.edges`.

Use this runbook to rebuild the graph from repository metadata, confirm the API gateway traversal endpoints, and emit derived degradation events for downstream services.

## Prerequisites

- Apply [`migrations/0012_graph_schema.sql`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0012_graph_schema.sql) to the shared Postgres database.
- Set `LV3_GRAPH_DSN` on the controller and Windmill worker environment.
- If the worker should enrich the graph from ADR 0113 surfaces, also set `WORLD_STATE_DSN`.
- If propagated health events should be recorded in the mutation ledger, set `LV3_LEDGER_DSN`.
- After replaying the ADR 0113 schema on the Windmill database, run `REFRESH MATERIALIZED VIEW world_state.current_view;` before validating ADR 0117 so the graph importers do not read an unpopulated world-state view.

## Rebuild The Graph

Run the repo-managed Windmill worker entrypoints directly when validating from a controller checkout:

```bash
python3 config/windmill/scripts/graph/import-from-catalog.py \
  --repo-path /srv/proxmox_florin_server
```

```bash
python3 config/windmill/scripts/graph/import-from-netbox.py \
  --repo-path /srv/proxmox_florin_server
```

Both entrypoints rebuild the full graph from the current repository checkout. The NetBox variant additionally folds in the latest `netbox_topology` and `dns_records` ADR 0113 surfaces when they are available.

If the Python environment on the worker does not already have the required dependencies, the wrappers fall back to `uv run --isolated --no-project` so the repo-managed scripts can still execute from the mounted checkout.

## Verify Stored Graph State

Check that the graph schema contains the expected first-class nodes and edges:

```sql
SELECT count(*) FROM graph.nodes;
SELECT count(*) FROM graph.edges;
SELECT ispopulated
FROM pg_matviews
WHERE schemaname = 'world_state'
  AND matviewname = 'current_view';
SELECT from_node, to_node, edge_kind
FROM graph.edges
WHERE to_node = 'service:postgres'
ORDER BY from_node;
```

On current mainline, `service:keycloak`, `service:netbox`, `service:mattermost`, and `service:windmill` should all appear as dependents of `service:postgres`.

`ispopulated` must be `t` before treating ADR 0117 as healthy. An unpopulated `world_state.current_view` causes the NetBox importer to fail even if the schema itself exists.

## Verify Traversal Queries

Use the graph client locally:

```bash
python3 - <<'PY'
from platform.graph import DependencyGraphClient

graph = DependencyGraphClient()
print(graph.descendants("service:postgres"))
print(graph.ancestors("service:ops_portal"))
print(graph.path("service:ops_portal", "service:postgres"))
PY
```

Or query through the platform API gateway once `LV3_GATEWAY_GRAPH_DSN` is configured:

```bash
curl -H "Authorization: Bearer <token>" https://api.lv3.org/v1/graph/nodes/service:postgres/descendants
curl -H "Authorization: Bearer <token>" "https://api.lv3.org/v1/graph/path?from_node=service:ops_portal&to_node=service:postgres"
```

When validating scheduled Windmill jobs, treat the database-backed `schedule.args` record as authoritative. The Windmill schedules list API can render `args: null` even while the persisted schedule arguments are present and the scheduled executions use them correctly.

## Propagate Derived Health

When the `service_health` world-state surface refreshes, run:

```bash
python3 config/windmill/scripts/graph/propagate-health.py \
  --repo-path /srv/proxmox_florin_server
```

The worker inspects degraded or down upstream services, walks their graph descendants, and emits `derived_health_degraded` events only for dependents whose own probes are still passing. If `LV3_LEDGER_DSN` is configured, it also writes `graph.health_propagated` records into `ledger.events`.

For ad hoc `run_wait_result` API calls, pass `dsn` and `world_state_dsn` explicitly in the request body instead of relying on ambient worker environment defaults.

## Notes

- `scripts/risk_scorer/context.py` now prefers `DependencyGraphClient().descendants()` when `LV3_GRAPH_DSN` is configured, and only falls back to the static repo graph if the runtime is unavailable.
- The graph importer intentionally rebuilds the whole graph on each run so duplicate edges do not accumulate between catalog and NetBox refresh cycles.
