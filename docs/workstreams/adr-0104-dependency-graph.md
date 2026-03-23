# Workstream ADR 0104: Service Dependency Graph and Failure Propagation Model

- ADR: [ADR 0104](../adr/0104-service-dependency-graph.md)
- Title: Machine-readable dependency graph with transitive impact analysis, deployment ordering, portal integration, and generated Mermaid documentation
- Status: ready
- Branch: `codex/adr-0104-service-dependency-graph`
- Worktree: `.worktrees/adr-0104`
- Owner: codex
- Depends On: `adr-0033-service-catalog`, `adr-0073-promotion-gate`, `adr-0093-interactive-ops-portal`, `adr-0094-developer-portal`
- Conflicts With: none
- Shared Surfaces: `config/`, `scripts/dependency_graph.py`, `scripts/promotion_pipeline.py`, `scripts/generate_ops_portal.py`, `scripts/platform_context_service.py`, `scripts/lv3_cli.py`

## Scope

- write `config/dependency-graph.json` — complete graph with all current platform services as nodes and all known edges
- write `scripts/dependency_impact.py` — transitive impact analysis: given a failed service, returns all affected services with classification (hard/soft/startup_only)
- write `scripts/validate_dependency_graph.py` — validates that every service in `config/service-capability-catalog.json` has a node in the dependency graph; added as a validation gate check
- write `scripts/generate_dependency_diagram.py` — generates a Mermaid diagram and Markdown page at `docs/site-generated/architecture/dependency-graph.md`
- update `scripts/promotion_pipeline.py` — add `deployment_order()` function using topological sort of the dependency graph
- add `config/dependency-graph.json` to the JSON schema validation gate
- add `/v1/platform/dependency-graph` and `/v1/platform/dependency-graph/{service}/impact` to the current private FastAPI surface
- add `lv3 impact <service>` command to the platform CLI (ADR 0090 integration)
- update `scripts/generate_ops_portal.py` — surface recovery tier and blast radius on service cards
- add `docs/runbooks/dependency-graph.md` — operator procedure for validation, impact analysis, regeneration, and ordering checks

## Non-Goals

- Real-time dependency discovery from network traffic
- Dependency tracking for individual containers within a service (service-to-service only)
- Automatic dependency graph updates (updates are triggered by the new service checklist in ADR 0107)

## Expected Repo Surfaces

- `config/dependency-graph.json`
- `docs/schema/service-dependency-graph.schema.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/runbooks/dependency-graph.md`
- `scripts/dependency_graph.py`
- `scripts/dependency_impact.py`
- `scripts/validate_dependency_graph.py`
- `scripts/generate_dependency_diagram.py`
- `scripts/promotion_pipeline.py` (patched: `deployment_order()`)
- `config/validation-gate.json` (patched: dependency graph validation check added)
- `scripts/platform_context_service.py` (patched: dependency graph routes added)
- `scripts/generate_ops_portal.py` (patched: dependency summaries shown on cards)
- `scripts/lv3_cli.py` (patched: `impact` command added)
- `docs/adr/0104-service-dependency-graph.md`
- `docs/workstreams/adr-0104-dependency-graph.md`

## Expected Live Surfaces

- `lv3 impact postgres` prints a list of all services affected by a Postgres failure
- `GET /v1/platform/dependency-graph` returns the full graph JSON from the current private FastAPI surface
- `GET /v1/platform/dependency-graph/<service>/impact` returns the blast radius for a failed service
- Mermaid dependency diagram is rendered into `docs/site-generated/architecture/dependency-graph.md`
- Deployment ordering uses topological sort
- The ops portal service cards show recovery tier and failure blast radius

## Verification

- `uv run --with jsonschema python scripts/dependency_impact.py --service postgres` → lists keycloak, windmill, netbox, mattermost, and transitively affected services
- `uv run --with jsonschema python scripts/validate_dependency_graph.py` → passes (all services in the capability catalog have a graph node)
- `uv run --with jsonschema python scripts/generate_dependency_diagram.py --check` → generated Markdown and Mermaid diagram are current
- Validation gate rejects a push that adds a service to the capability catalog without a corresponding dependency graph node

## Merge Criteria

- All current platform services (23) have nodes in `config/dependency-graph.json`
- All known hard dependencies have edges
- `validate_dependency_graph.py` passes
- `lv3 impact postgres` returns the expected list
- Mermaid diagram renders without errors
- Portal generation tests pass with the dependency summaries included

## Notes For The Next Assistant

- Repo implementation is complete in `0.108.0`; no live platform version bump has been recorded yet.
- The `/v1/platform/dependency-graph*` routes still ride on `platform_context_service.py`; ADR 0092 now fronts public APIs, but the dependency-graph endpoints have not yet been re-homed under the gateway.
- The generated documentation page is validated both by `scripts/generate_dependency_diagram.py --check` and through the ADR 0094 docs-site build path.
