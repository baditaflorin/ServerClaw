# Workstream ws-0327-live-apply: Live Apply ADR 0327 From Latest `origin/main`

- ADR: [ADR 0327](../adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md)
- Title: Sectional agent discovery registries and generated onboarding packs
- Status: in_progress
- Included In Repo Version: pending main integration
- Live Applied In Platform Version: N/A
- Implemented On: pending
- Live Applied On: pending
- Branch: `codex/ws-0327-live-apply`
- Worktree: `.worktrees/ws-0327-live-apply`
- Owner: codex
- Depends On: `adr-0163-repository-structure-index-for-agent-discovery`, `adr-0166-canonical-configuration-locations-registry`, `adr-0168-automated-enforcement-of-agent-standards`, `adr-0335-public-safe-agent-onboarding-entrypoints`, `adr-0336-public-entrypoint-leakage-validation`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0327-live-apply.md`, `docs/adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md`, `docs/adr/.index.yaml`, `docs/runbooks/discovery-registry-maintenance.md`, `.gitignore`, `.repo-structure.yaml`, `.config-locations.yaml`, `docs/diagrams/agent-coordination-map.excalidraw`, `docs/discovery/`, `build/onboarding/`, `scripts/generate_discovery_artifacts.py`, `scripts/label_studio_sync.py`, `scripts/validate_public_entrypoints.py`, `scripts/validate_repo.sh`, `tests/test_generate_discovery_artifacts.py`, `tests/test_label_studio_sync.py`, `tests/test_validate_public_entrypoints.py`, `tests/test_validate_repo_cache.py`, `receipts/live-applies/2026-04-03-adr-0327-sectional-agent-discovery-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-ws-0327-*`

## Scope

- split the monolithic discovery entrypoints into canonical concern-based source registries under `docs/discovery/`
- generate concise root `.repo-structure.yaml` and `.config-locations.yaml` entrypoints from those section files
- generate task-shaped onboarding packs under `build/onboarding/`
- wire discovery generation into the repo validation path and keep the new onboarding sources public-safe and repository-portable
- record branch-local live-apply evidence and merge notes without touching protected release surfaces on the workstream branch

## Non-Goals

- changing top-level `README.md` integrated status summaries on this workstream branch
- bumping `VERSION`, editing release sections in `changelog.md`, or updating `versions/stack.yaml` before an exact-main integration step
- implementing the other ADR 0324 roadmap items for ADR indexing, workstream sharding, or root-summary rollover in this same workstream

## Expected Repo Surfaces

- `docs/discovery/repo-structure/`
- `docs/discovery/config-locations/`
- `docs/discovery/onboarding-packs.yaml`
- `.gitignore`
- `.repo-structure.yaml`
- `.config-locations.yaml`
- `build/onboarding/agent-core.yaml`
- `build/onboarding/automation.yaml`
- `build/onboarding/service-catalog.yaml`
- `scripts/generate_discovery_artifacts.py`
- `scripts/validate_public_entrypoints.py`
- `scripts/validate_repo.sh`
- `docs/runbooks/discovery-registry-maintenance.md`
- `docs/adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md`
- `docs/adr/.index.yaml`
- `tests/test_generate_discovery_artifacts.py`
- `tests/test_validate_public_entrypoints.py`
- `tests/test_validate_repo_cache.py`
- `receipts/live-applies/`

## Expected Live Apply Outcome

- the current worktree can regenerate the root discovery entrypoints and onboarding packs deterministically from `docs/discovery/`
- `scripts/validate_repo.sh agent-standards` fails closed if the generated discovery artifacts drift or if discovery entrypoints leak absolute paths or deployment-specific identifiers
- the focused discovery/onboarding tests pass from the clean worktree
- `make validate`, `make remote-validate`, and `make pre-push-gate` can be rerun from the exact-main integration step after protected release surfaces are updated, if needed

## Verification Plan

- regenerate discovery artifacts from the new canonical source directories
- run `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`
- run `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_generate_discovery_artifacts.py tests/test_validate_public_entrypoints.py tests/test_validate_repo_cache.py`
- run `./scripts/validate_repo.sh agent-standards generated-docs`
- run `git diff --check`
- record the command receipts and the resulting generated outputs in `receipts/live-applies/`

## Merge Notes

- protected release surfaces remain untouched on this workstream branch by design: `VERSION`, release sections in `changelog.md`, the top-level README integrated-status summary, and `versions/stack.yaml`
- if this workstream becomes the final exact-main integration step, stamp ADR 0327 with the merged repo version and final implementation date, then update the release files on `main`
- because ADR 0327 is repository-only discovery tooling, `Implemented In Platform Version` should remain `N/A` unless a future platform process assigns repo-only governance changes a platform version
