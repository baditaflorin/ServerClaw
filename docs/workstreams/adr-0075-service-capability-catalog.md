# Workstream ADR 0075: Service Capability Catalog

- ADR: [ADR 0075](../adr/0075-service-capability-catalog.md)
- Title: Machine-readable index of every platform service with URLs, ownership, health probes, and runbook links
- Status: ready
- Branch: `codex/adr-0075-service-capability-catalog`
- Worktree: `../proxmox_florin_server-service-capability-catalog`
- Owner: codex
- Depends On: `adr-0064-health-probe-contracts`, `adr-0068-container-image-policy`, `adr-0065-secret-rotation-automation`
- Conflicts With: none
- Shared Surfaces: `config/`, `docs/schema/`, `scripts/validate_repo.sh`, `Makefile`

## Scope

- define JSON schema in `docs/schema/service-capability-catalog.schema.json`
- populate `config/service-capability-catalog.json` with all currently-running services (minimum 12 entries covering all live-applied services)
- write `scripts/validate_service_catalog.py` to cross-reference health-probe-catalog, image-catalog, secret-catalog, and runbook paths
- add validation to `make validate`
- add `make show-service SERVICE=<id>` query target for agent and operator use
- document the catalog schema and maintenance process in `docs/runbooks/service-capability-catalog.md`

## Non-Goals

- service-to-service dependency graphs (first iteration: discovery only)
- runtime topology updates (catalog is updated manually or via scaffold generator, not auto-discovered)

## Expected Repo Surfaces

- `config/service-capability-catalog.json`
- `docs/schema/service-capability-catalog.schema.json`
- `scripts/validate_service_catalog.py`
- updated `scripts/validate_repo.sh`
- `docs/runbooks/service-capability-catalog.md`
- `docs/adr/0075-service-capability-catalog.md`
- `docs/workstreams/adr-0075-service-capability-catalog.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no live changes; this is a repository-only catalog and validation gate

## Verification

- `make validate` catches a catalog entry with a broken `health_probe_id` reference
- `make show-service SERVICE=grafana` returns a readable summary of the Grafana service entry
- all 12+ live-applied services have valid catalog entries
- JSON Schema validation passes for the full catalog file

## Merge Criteria

- all live-applied services are represented in the catalog
- all cross-references (health probes, images, secrets, runbooks) resolve
- the validation script is integrated into `make validate` and documented
- at least one validation failure is demonstrated in a test fixture

## Notes For The Next Assistant

- populate the catalog by reading `versions/stack.yaml`, `config/uptime-kuma/monitors.json`, and existing runbooks — most data already exists, it just needs to be assembled into the schema
- start with services that have the most complete data (grafana, uptime-kuma, openbao) and work toward those with gaps
- the cross-reference validation is the most valuable part; build that before the full catalog is complete
