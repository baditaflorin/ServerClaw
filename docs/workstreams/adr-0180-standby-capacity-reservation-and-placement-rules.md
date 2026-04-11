# Workstream ADR 0180: Standby Capacity Reservation and Placement Rules

- ADR: [ADR 0180](../adr/0180-standby-capacity-reservation-and-placement-rules.md)
- Title: Reserve standby capacity and enforce placement rules before live apply
- Status: implemented
- Branch: `codex/adr-0180-standby-capacity`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0180-standby-capacity`
- Owner: codex
- Depends On: `adr-0105-capacity-model`, `adr-0157-per-vm-concurrency-budget`, `adr-0179-service-redundancy-tier-matrix`
- Conflicts With: none
- Shared Surfaces: `config/service-capability-catalog.json`, `config/capacity-model.json`, `docs/schema/{service-capability-catalog,capacity-model}.schema.json`, `scripts/{capacity_report,service_catalog,standby_capacity,promotion_pipeline}.py`, `Makefile`, `docs/runbooks/capacity-model.md`

## Scope

- add a machine-readable standby declaration for `R2` and higher services
- validate standby placement rules and same-host failure-domain honesty
- let production `live-apply-service` fail fast when standby backing is missing or conflicting
- cover projected standby headroom under simulated load in tests

## Non-Goals

- choosing the redundancy tier for every service in the platform
- changing live infrastructure or claiming off-host redundancy
- implementing automated failover orchestration

## Verification

- `python3 scripts/standby_capacity.py --validate`
- `python3 -m pytest tests/test_capacity_report.py tests/test_standby_capacity.py tests/test_validate_service_catalog.py tests/test_promotion_pipeline.py -q`

## Outcome

- repository implementation completed in `0.176.4`
- PostgreSQL now declares an `R2` warm standby backed by `postgres-replica`
- production service live applies now run a standby-capacity guard before Ansible execution
