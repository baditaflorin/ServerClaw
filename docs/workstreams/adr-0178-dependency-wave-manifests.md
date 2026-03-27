# Workstream ADR 0178: Dependency Wave Manifests

- ADR: [ADR 0178](../adr/0178-dependency-wave-manifests-for-parallel-apply.md)
- Title: Manifest-driven parallel live apply with explicit wave ordering, shard validation, and lock prechecks
- Status: merged
- Branch: `codex/adr-0178-dependency-wave`
- Worktree: `../worktree-adr-0178-dependency-wave`
- Owner: codex
- Depends On: `adr-0153-distributed-resource-lock-registry`, `adr-0154-vm-scoped-execution-lanes`, `adr-0176-inventory-sharding`
- Conflicts With: `adr-0176-inventory-sharding`, `adr-0182-live-apply-merge-train`
- Shared Surfaces: `platform/ansible/`, `scripts/dependency_wave_apply.py`, `Makefile`, `config/workflow-catalog.json`, `config/dependency-wave-playbooks.yaml`, `docs/runbooks/dependency-wave-parallel-apply.md`

## Scope

- add a dependency-wave manifest model with DAG validation and stable topological ordering
- add a playbook apply metadata catalog plus fallback resolution for service, group, site, and top-level converge playbooks
- add a controller-local executor that pre-acquires wave locks, heartbeats them during execution, and fans out same-wave playbooks in parallel
- add a `make live-apply-waves` entrypoint and an example manifest
- add focused tests for graph ordering, same-wave parallelism, shard rejection, blocking locks, and partial-safe continuation

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_dependency_wave_apply.py -q`
- `uv run --with pyyaml python scripts/dependency_wave_apply.py --manifest config/dependency-waves/security-observability-bootstrap.yaml --dry-run`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Outcome

- merged in repo version `0.176.1`
- no live platform apply performed from `main` in this turn
