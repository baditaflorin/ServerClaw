# Workstream ws-0212-live-apply: ADR 0212 Live Apply From Latest `origin/main`

- ADR: [ADR 0212](../adr/0212-replaceability-scorecards-and-vendor-exit-plans.md)
- Title: enforce replaceability scorecards and vendor exit plans for critical integrated product ADRs, then publish the updated governance docs live
- Status: in_progress
- Branch: `codex/ws-0212-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0212-live-apply`
- Owner: codex
- Depends On: `adr-0205-capability-contracts-before-product-selection`, `adr-0213-architecture-fitness-functions-in-the-validation-gate`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0212-replaceability-scorecards-and-vendor-exit-plans.md`, `config/replaceability-review-catalog.json`, `scripts/replaceability_scorecards.py`, `docs/runbooks/replaceability-scorecards.md`, `receipts/live-applies/`

## Scope

- define the governed set of critical integrated product ADRs that must carry replaceability scorecards and exit plans
- add the repo fitness function and validation-gate wiring that enforce those sections automatically
- backfill the governed ADR set with concrete scorecards and exit plans
- publish the resulting ADR updates to the live docs portal from this workstream branch and verify the deployed output on the edge host
- leave protected integration files alone on the workstream branch while recording exactly what the later merge-to-main step still needs

## Non-Goals

- backfilling every historical product ADR in one pass regardless of current criticality or integrated status
- claiming ADR 0205 is fully implemented everywhere a capability contract might eventually exist
- rewriting unrelated release metadata on the workstream branch

## Expected Repo Surfaces

- `config/replaceability-review-catalog.json`
- `docs/schema/replaceability-review-catalog.schema.json`
- `scripts/replaceability_scorecards.py`
- `tests/test_replaceability_scorecards.py`
- `scripts/validate_repository_data_models.py`
- `scripts/validate_repo.sh`
- `platform/interface_contracts.py`
- `Makefile`
- `docs/runbooks/replaceability-scorecards.md`
- `docs/runbooks/validate-repository-automation.md`
- `collections/ansible_collections/lv3/platform/roles/_template/service_scaffold/adr.md.tpl`
- `tests/test_interface_contracts.py`
- `tests/test_scaffold_service.py`
- `docs/adr/0212-replaceability-scorecards-and-vendor-exit-plans.md`
- `docs/adr/0213-architecture-fitness-functions-in-the-validation-gate.md`
- selected governed product ADRs listed in `config/replaceability-review-catalog.json`
- `docs/adr/.index.yaml`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/workstreams/ws-0212-live-apply.md`

## Expected Live Surfaces

- `docs.lv3.org` serves the updated governed ADR pages with their replaceability scorecards and vendor exit plans
- the edge host carries the refreshed generated docs content for the governed ADR paths

## Ownership Notes

- this workstream owns the replaceability catalog, validator, runbook, receipt, and the governed ADR backfill set
- repo validation surfaced a pre-existing workstream-status enum mismatch, so this workstream also owns the minimal contract/test fix needed to let `in_progress` workstreams validate cleanly
- protected integration files still stay out of scope on the branch even if the live docs portal publish succeeds
- the live publish is bounded to existing docs publication infrastructure and does not introduce a new production service

## Verification

- `python3 scripts/replaceability_scorecards.py --validate`
- `python3 scripts/replaceability_scorecards.py --report`
- `uv run --with pytest python -m pytest tests/test_interface_contracts.py tests/test_replaceability_scorecards.py tests/test_scaffold_service.py tests/test_validate_repo_cache.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh architecture-fitness agent-standards workstream-surfaces`
- `./scripts/validate_repo.sh generated-portals`
- `make docs`
- `make deploy-docs-portal`

## Merge Criteria

- the governed ADR set is machine-readable instead of being implied by title conventions
- validation fails closed when a governed ADR loses one of the required scorecard or exit-plan fields
- the docs portal publish and edge-host verification prove the updated governance guidance reached the live platform

## Notes For The Next Assistant

- pull from `origin/main` again before the final merge step because other agents are actively updating generated and release-adjacent surfaces
- if `make deploy-docs-portal` touches integration-owned generated pages outside this scope, record the exception and keep the branch focused on ADR 0212-owned governance surfaces
