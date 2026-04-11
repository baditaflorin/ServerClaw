# Workstream ADR 0179: Service Redundancy Tier Matrix

- ADR: [ADR 0179](../adr/0179-service-redundancy-tier-matrix.md)
- Title: machine-readable service redundancy tiers, tier-aware live-apply gating, and operator runbooks
- Status: merged
- Branch: `codex/adr-0179-redundancy-tier`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0179-redundancy-tier`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0100-rto-rpo-targets-and-disaster-recovery-playbook`
- Conflicts With: none
- Shared Surfaces: `config/service-redundancy-catalog.json`, `docs/schema/service-redundancy-catalog.schema.json`, `scripts/service_redundancy.py`, `Makefile`, `scripts/validate_repository_data_models.py`, `docs/runbooks/service-redundancy-tier-matrix.md`, `docs/runbooks/deploy-a-service.md`

## Scope

- create the machine-readable service redundancy catalog for every managed service
- validate tier declarations against the current service inventory and single-host platform limit
- make `live-apply-*` fail fast when a declared tier exceeds what the platform can honestly support
- document how operators update and inspect the redundancy matrix

## Non-Goals

- implementing new warm standbys beyond the ones the platform already has
- changing the live platform version or claiming that new redundancy has already been applied live
- inventing a fake `R3` story before a second failure domain exists

## Expected Repo Surfaces

- `config/service-redundancy-catalog.json`
- `docs/schema/service-redundancy-catalog.schema.json`
- `scripts/service_redundancy.py`
- `scripts/validate_repository_data_models.py`
- `Makefile`
- `docs/runbooks/service-redundancy-tier-matrix.md`
- `docs/runbooks/deploy-a-service.md`
- `docs/runbooks/service-capability-catalog.md`
- `docs/adr/0179-service-redundancy-tier-matrix.md`
- `docs/workstreams/adr-0179-service-redundancy-tier-matrix.md`
- `tests/test_service_redundancy.py`

## Expected Live Surfaces

- future production `live-apply-*` runs refuse unsupported redundancy claims before they start Ansible
- warm-standby services continue to advertise their standby-aware deployment mode during preflight

## Verification

- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --validate`
- `uv run --with pytest --with pyyaml --with jsonschema pytest tests/test_service_redundancy.py tests/test_validate_service_catalog.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- every service in `config/service-capability-catalog.json` has a matching redundancy declaration
- the single-host platform limit is enforced in the live-apply preflight
- operator documentation explains how to inspect and update the matrix

## Outcome

- repository implementation is complete on `main` in repo release `0.176.5`
- platform version remains unchanged until a later live apply from `main` carries the new preflight into production

## Notes For The Next Assistant

- `R2` is currently honest only for PostgreSQL because `postgres-replica` already exists and participates in Patroni failover.
- `R3` handling is intentionally strict in live apply: the catalog may describe future intent, but deployment will not treat it as implemented on a single host.
