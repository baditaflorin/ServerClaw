# Workstream ADR 0075: Service Capability Catalog

- ADR: [ADR 0075](../adr/0075-service-capability-catalog.md)
- Title: Machine-readable index of every platform service with URLs, ownership, health probes, and runbook links
- Status: merged
- Branch: `codex/adr-0075-service-capability-catalog`
- Worktree: `../proxmox_florin_server-service-capability-catalog`
- Owner: codex
- Depends On: `adr-0064-health-probe-contracts`, `adr-0068-container-image-policy`, `adr-0065-secret-rotation-automation`
- Conflicts With: none
- Shared Surfaces: `config/service-capability-catalog.json`, `docs/schema/service-capability-catalog.schema.json`, `scripts/validate_service_catalog.py`, `Makefile`

## Scope

- define a canonical schema for the service capability catalog
- populate the catalog with the current platform service estate
- validate runbook paths, health-probe references, image references, secret references, and topology alignment
- add operator and agent query affordances through `make services` and `make show-service`
- document maintenance and validation in a dedicated runbook

## Non-Goals

- service-to-service dependency graphs
- automatic runtime discovery that mutates the catalog
## Expected Repo Surfaces

- `config/service-capability-catalog.json`
- `docs/schema/service-capability-catalog.schema.json`
- `scripts/service_catalog.py`
- `scripts/validate_service_catalog.py`
- updated `scripts/validate_repo.sh`
- `docs/runbooks/service-capability-catalog.md`
- `docs/adr/0075-service-capability-catalog.md`
- `docs/workstreams/adr-0075-service-capability-catalog.md`
- `workstreams.yaml`

## Expected Live Surfaces

- none; this is a repository contract and validation surface

## Verification

- `make services`
- `make show-service SERVICE=grafana`
- `uv run --with pyyaml --with jsonschema python scripts/service_catalog.py --validate`
- `uv run --with pyyaml --with jsonschema python -m unittest tests/test_validate_service_catalog.py`
- `make validate`

## Merge Criteria

- all 19 health-probe-catalog services are represented in the catalog
- monitor names, runbooks, topology links, and cross-catalog references validate cleanly
- validation is wired into the repository gate
- ADR metadata records the original repository implementation in `0.69.0` and the current-main completion in `0.72.0`

## Delivered

- extended `config/service-capability-catalog.json` to cover the current 19 health-probe-backed services on `main`
- upgraded `scripts/service_catalog.py` to validate the JSON Schema plus health-probe, image, secret, monitor, runbook, and topology cross-references
- added `make services`, focused service-catalog regression tests, and a negative broken-health-probe fixture
- updated the ADR, runbook, workstream metadata, and release files to reflect the current-main completion in `0.72.0`
