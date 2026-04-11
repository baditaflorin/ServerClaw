# Workstream WS-0373: Service Registry Live Apply

- ADR: [ADR 0373](../adr/0373-service-registry-and-derived-defaults.md)
- Title: Service Registry and Derived Defaults
- Status: in_progress
- Branch: `codex/ws-0373-live-apply`
- Worktree: `.worktrees/ws-0373-live-apply`
- Owner: `codex`
- Depends On: `adr-0344-single-source-environment-topology`, `adr-0359-declarative-postgresql-client-registry`
- Conflicts With: none
- Shared Surfaces: `inventory/group_vars/all/platform_services.yml`, `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`, `scripts/validate_service_registry.py`, `docs/adr/0373-service-registry-and-derived-defaults.md`, `docs/runbooks/add-new-service-to-platform.md`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- validate the latest `origin/main` ADR 0373 codepath from an isolated worktree
- replay the governed production live-apply path for the service-registry pattern
- verify representative current-platform services and automation paths end to end
- leave merge-safe evidence and metadata even though ADR 0407 removed `receipts/` from the default committed surface

## Non-Goals

- re-implementing ADR 0373 from scratch when the code is already merged on `origin/main`
- bumping `VERSION`, editing release sections in `changelog.md`, or changing the top-level `README.md` summary before final integration on `main`
- broad unrelated platform changes outside the service-registry/defaults contract

## Expected Repo Surfaces

- `workstreams/active/ws-0373-live-apply.yaml`
- `docs/workstreams/ws-0373-live-apply.md`
- `docs/adr/0373-service-registry-and-derived-defaults.md`
- `docs/adr/implementation-status/adr-0373.yaml`
- `docs/postmortems/adr-0373-service-registry-adoption-completion.md`
- `docs/runbooks/add-new-service-to-platform.md`
- `inventory/group_vars/all/platform_services.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`
- `scripts/validate_service_registry.py`
- `scripts/validate_repo.sh`
- `tests/test_validate_service_completeness.py`
- `tests/test_ansible_execution_scopes.py`
- `workstreams.yaml`
- `receipts/live-applies/`

## Expected Live Surfaces

- the current production converge path can apply latest-main ADR 0373 state without undefined-variable regressions
- representative live services across the current platform still derive conventional defaults correctly from the registry
- repo automation and validation entrypoints that guard ADR 0373 remain green from the isolated worktree

## Verification

- Repo preparation completed from latest `origin/main` (`59fbe662b`).
- Passed:
  - `python3 scripts/validate_service_registry.py --check`
  - `uv run --with pytest --with pyyaml python -m pytest -q tests/test_validate_service_registry.py tests/test_validate_service_completeness.py tests/test_ansible_execution_scopes.py`
  - `uv run --with pyyaml python scripts/ansible_scope_runner.py validate`
  - `./scripts/run_python_with_packages.sh pyyaml jsonschema -- scripts/service_redundancy.py --validate`
  - `scripts/validate_public_entrypoints.py --check`
  - `./scripts/validate_repo.sh agent-standards`
- Current inherited gap:
  - `./scripts/validate_repo.sh data-models` still fails in the local validation harness because the ignored `receipts/live-applies/` archive is incomplete after ADR 0407 and several historical receipt evidence refs still target renamed/removed files. The ADR 0373 codepaths and current catalog validators now pass; the remaining failure is receipt-history drift rather than a live service-registry regression.

## Live Apply Outcome

- pending

## Live Evidence

- Repo-side ADR 0373 fixes before live replay:
  - `scripts/validate_service_registry.py` now validates current inventory-aware host groups and service-type-specific requirements correctly on latest `origin/main`.
  - `config/ansible-execution-scopes.yaml` now includes the missing scopes required by the current repo validator.
  - `scripts/generate_platform_vars.py` and `scripts/service_redundancy.py` both now avoid the stdlib `platform` import shadowing bug that blocked validation from an isolated worktree.
  - `config/image-catalog.json` placeholder entries for `librechat_runtime` and `litellm_runtime` now use a validator-compatible scaffold state so the image-policy path can be exercised from this branch before final pin/scan.
  - `config/service-redundancy-catalog.json` is back in schema shape and now includes current-main `librechat`, `litellm`, and `neko` entries.
  - `config/health-probe-catalog.json`, `config/workbench-information-architecture.json`, and `config/correction-loops.json` were repaired where current-main drift blocked ADR 0373 validation lanes.

## Mainline Integration Notes

- protected integration files remain untouched on this branch until the final verified integration step
- if the production replay succeeds, update ADR 0373 metadata plus implementation-status state on this branch, then reserve `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml` for the final `main` integration step only
