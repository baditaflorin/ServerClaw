# Workstream ADR 0117: Service Dependency Graph As First-Class Runtime

- ADR: [ADR 0117](../adr/0117-service-dependency-graph-runtime.md)
- Title: Persist a machine-usable DAG of service/host/network/cert dependencies in Postgres; expose traversal API for blast-radius, health propagation, and incident correlation used by triage and risk scoring
- Status: ready
- Branch: `codex/adr-0117-dependency-graph`
- Worktree: `../proxmox_florin_server-dependency-graph`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0054-netbox-topology`, `adr-0058-nats-event-bus`, `adr-0075-service-capability-catalog`, `adr-0092-platform-api-gateway`, `adr-0098-postgres-ha`, `adr-0113-world-state-materializer`
- Conflicts With: `adr-0113-world-state-materializer` (both read from NetBox; coordinate on refresh timing to avoid stampede)
- Shared Surfaces: `platform/graph/`, `graph.nodes` and `graph.edges` Postgres schema, `config/dependency-graph.yaml`, `/v1/graph/*` API gateway endpoints

## Scope

- create Postgres migration `migrations/0012_graph_schema.sql` — `graph.nodes` and `graph.edges` tables with indexes from ADR 0117
- create `config/dependency-graph.yaml` — initial manual edge declarations for all platform services (netbox→postgres, keycloak→postgres, windmill→postgres, mattermost→postgres, grafana→loki, grafana→prometheus, all services→step-ca, all services→docker-runtime-lv3)
- create `platform/graph/__init__.py`
- create `platform/graph/client.py` — `DependencyGraphClient` with `descendants()`, `ancestors()`, `path()`, `neighbourhood()`, `health_propagation()` methods using recursive CTEs
- create `windmill/graph/import-from-netbox.py` — Windmill workflow: imports device→rack, IP, VLAN edges from NetBox world-state snapshot
- create `windmill/graph/import-from-catalog.py` — Windmill workflow: imports `depends_on` edges from `config/workflow-catalog.json`
- create `windmill/graph/propagate-health.py` — Windmill workflow subscribed to `world_state.refreshed` on `service_health` surface; runs health propagation and emits `derived_health_degraded` NATS events
- register `/v1/graph/*` routes on the platform API gateway (ADR 0092): `GET /v1/graph/nodes`, `GET /v1/graph/nodes/{id}/descendants`, `GET /v1/graph/nodes/{id}/ancestors`, `GET /v1/graph/nodes/{id}/health`, `GET /v1/graph/path`
- write `tests/unit/test_graph_client.py` — test recursive traversal, cycle detection, empty graph, single-node graph

## Non-Goals

- Code-level or build-time dependency analysis
- Replacing NetBox as the topology source of truth
- Real-time edge updates (graph is rebuilt from sources on each refresh cycle, not updated incrementally)

## Expected Repo Surfaces

- `migrations/0012_graph_schema.sql`
- `config/dependency-graph.yaml`
- `platform/graph/__init__.py`
- `platform/graph/client.py`
- `windmill/graph/import-from-netbox.py`
- `windmill/graph/import-from-catalog.py`
- `windmill/graph/propagate-health.py`
- `docs/adr/0117-service-dependency-graph-runtime.md`
- `docs/workstreams/adr-0117-dependency-graph-runtime.md`

## Expected Live Surfaces

- `graph.nodes` contains rows for all platform services, VMs, and hosts
- `graph.edges` contains at minimum all `depends_on` edges declared in `config/dependency-graph.yaml`
- `DependencyGraphClient().descendants("service:postgres")` returns the correct set of dependent services
- `GET /v1/graph/nodes/service:postgres/descendants` via the API gateway returns the same set
- Stopping the health probe for a service causes a `derived_health_degraded` NATS event for its dependents within 60 seconds

## Verification

- Run `pytest tests/unit/test_graph_client.py -v` → all tests pass
- Confirm `SELECT count(*) FROM graph.nodes;` returns at least 15 rows after the import workflows run
- Call `DependencyGraphClient().descendants("service:postgres")` → verify keycloak, netbox, windmill, mattermost all appear
- Simulate a health probe failure for postgres (set `available: false` in a test snapshot) → confirm `derived_health_degraded` NATS events arrive for downstream services within the propagation window

## Merge Criteria

- Unit tests pass including cycle-detection test
- Graph populated for all current platform services
- Health propagation verified end-to-end
- API gateway endpoints responding with correct data
- Risk scorer (ADR 0116) `downstream_count` stub replaced with real `DependencyGraphClient().descendants()` call

## Notes For The Next Assistant

- Recursive CTEs for `descendants()` must have a cycle guard: include a `visited` set in the CTE to avoid infinite loops if a graph cycle is ever introduced by a bad import. Log a warning and return the partial result rather than crashing.
- The `health_propagation()` method should only propagate `degraded` status, not `down`. A `down` service means the health probe is failing; a `derived_health_degraded` on a downstream service means "your upstream is sick, you might be at risk". Conflating these two statuses in triage signals would cause confusion.
- The `import-from-catalog.py` workflow reads `config/workflow-catalog.json` which is on disk in the repo. In Windmill, this means the workflow must clone or read the repo via the git resource. Coordinate with the platform API gateway workstream to ensure the catalog is also accessible via `/v1/platform/catalog`.
- Edge de-duplication: the import workflows run on a schedule and re-insert edges. Use `INSERT INTO graph.edges ... ON CONFLICT DO NOTHING` to avoid duplicate edges accumulating over time.
