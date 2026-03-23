# Workstream ADR 0104: Service Dependency Graph and Failure Propagation Model

- ADR: [ADR 0104](../adr/0104-service-dependency-graph.md)
- Title: Machine-readable DAG in dependency-graph.json with transitive impact analysis, deployment ordering, and Mermaid diagram for the docs site
- Status: ready
- Branch: `codex/adr-0104-dependency-graph`
- Worktree: `../proxmox_florin_server-dependency-graph`
- Owner: codex
- Depends On: `adr-0033-service-catalog`, `adr-0073-promotion-gate`, `adr-0093-interactive-ops-portal`, `adr-0094-developer-portal`
- Conflicts With: none
- Shared Surfaces: `config/`, `scripts/promotion_pipeline.py`, `scripts/generate_docs_site.py`

## Scope

- write `config/dependency-graph.json` — complete graph with all current platform services as nodes and all known edges
- write `scripts/dependency_impact.py` — transitive impact analysis: given a failed service, returns all affected services with classification (hard/soft/startup_only)
- write `scripts/validate_dependency_graph.py` — validates that every service in `config/service-capability-catalog.json` has a node in the dependency graph; added as a validation gate check
- write `scripts/generate_dependency_diagram.py` — generates a Mermaid diagram from the graph JSON for the docs site
- update `scripts/promotion_pipeline.py` — add `deployment_order()` function using topological sort of the dependency graph
- add `config/dependency-graph.json` to the JSON schema validation gate
- add `/v1/platform/dependency-graph` endpoint to the API gateway
- add `lv3 impact <service>` command to the platform CLI (ADR 0090 integration)
- update docs site generation (`scripts/generate_docs_site.py`) — include the Mermaid diagram in `docs/site-generated/architecture/dependency-graph.md`

## Non-Goals

- Real-time dependency discovery from network traffic
- Dependency tracking for individual containers within a service (service-to-service only)
- Automatic dependency graph updates (updates are triggered by the new service checklist in ADR 0107)

## Expected Repo Surfaces

- `config/dependency-graph.json`
- `scripts/dependency_impact.py`
- `scripts/validate_dependency_graph.py`
- `scripts/generate_dependency_diagram.py`
- `scripts/promotion_pipeline.py` (patched: `deployment_order()`)
- `config/validation-gate.json` (patched: dependency graph validation check added)
- `docs/adr/0104-service-dependency-graph.md`
- `docs/workstreams/adr-0104-dependency-graph.md`

## Expected Live Surfaces

- `lv3 impact postgres` prints a list of all services affected by a Postgres failure
- `GET /v1/platform/dependency-graph` returns the full graph JSON
- Mermaid dependency diagram is rendered in the docs site architecture section
- Deployment ordering uses topological sort (verify by deploying two co-dependent services and checking order)

## Verification

- `python3 scripts/dependency_impact.py --service postgres` → lists keycloak, windmill, netbox, mattermost, and all transitively affected services
- `python3 scripts/validate_dependency_graph.py` → passes (all services in the capability catalog have a graph node)
- `python3 scripts/generate_dependency_diagram.py` → produces valid Mermaid syntax (validate with mermaid-js CLI or online parser)
- Validation gate rejects a push that adds a service to the capability catalog without a corresponding dependency graph node

## Merge Criteria

- All current platform services (20+) have nodes in `config/dependency-graph.json`
- All known hard dependencies have edges
- `validate_dependency_graph.py` passes
- `lv3 impact postgres` returns the expected list
- Mermaid diagram renders without errors

## Notes For The Next Assistant

- Populate the graph by working through the ADRs and service roles; for each service, its hard dependencies are typically: the database it connects to, the identity provider it uses (Keycloak), and any secrets provider (OpenBao via startup_only)
- The topological sort in `deployment_order()` must handle cycles gracefully — if a cycle exists in the graph (there should not be, but validation should check), raise a clear error rather than hanging
- The Mermaid diagram will be large (20+ nodes); consider splitting into sub-diagrams by tier for readability: one diagram for Tier 1-2, one for Tier 3-4, one for Tier 5
- Add a JSON Schema for `config/dependency-graph.json` to `config/schemas/` to enable schema validation in the gate
