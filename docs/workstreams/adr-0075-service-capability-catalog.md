# Workstream ADR 0075: Service Capability Catalog

- ADR: [ADR 0075](../adr/0075-service-capability-catalog.md)
- Title: Machine-readable index of every platform service with URLs, ownership, health monitors, and runbook links
- Status: merged
- Branch: `codex/adr-0074-ops-portal`
- Worktree: `../proxmox_florin_server__adr_0074`
- Owner: codex
- Depends On: `adr-0064-health-probe-contracts`, `adr-0068-container-image-policy`, `adr-0065-secret-rotation-automation`
- Conflicts With: none
- Shared Surfaces: `config/service-capability-catalog.json`, `docs/schema/service-capability-catalog.schema.json`, `scripts/validate_service_catalog.py`, `Makefile`

## Scope

- define a canonical schema for the service capability catalog
- populate the catalog with the current platform service estate
- validate runbook paths, monitor references, and topology alignment
- add operator and agent query affordances through `make show-service`
- document maintenance and validation in a dedicated runbook

## Non-Goals

- service-to-service dependency graphs
- automatic runtime discovery that mutates the catalog
- requiring image or secret references before those catalogs are canonical on `main`

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

- `make show-service SERVICE=grafana`
- `uvx --from pyyaml python scripts/service_catalog.py --validate`
- `uvx --from pyyaml python -m unittest discover -s tests -p 'test_*.py'`
- `make validate`

## Merge Criteria

- live-applied services are represented in the catalog
- monitor names, runbooks, and topology links validate cleanly
- validation is wired into the repository gate
- ADR metadata shows repository implementation in release `0.68.0`

## Notes For The Next Assistant

- repository implementation is merged by `0.68.0`
- image and secret catalog references remain optional until those dedicated catalogs become canonical on `main`
