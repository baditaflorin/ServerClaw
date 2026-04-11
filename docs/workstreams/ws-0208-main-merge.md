# Workstream ws-0208-main-merge

- ADR: [ADR 0208](../adr/0208-dependency-direction-and-composition-roots.md)
- Title: Integrate ADR 0208 dependency direction and composition roots into `origin/main`
- Status: merged
- Branch: `codex/ws-0208-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0208-main-merge`
- Owner: codex
- Depends On: `ws-0208-live-apply`
- Conflicts With: none

## Purpose

Carry the verified ADR 0208 workstream into the latest `origin/main`, refresh the protected release and canonical-truth files from the integrated candidate, and rerun the repository validation and automation paths from the rebased main-merge worktree before pushing the final fast-forward to `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0208-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.40.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `docs/adr/0208-dependency-direction-and-composition-roots.md`
- `docs/workstreams/ws-0208-live-apply.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/validate-repository-automation.md`
- `config/validation-gate.json`
- `Makefile`
- `config/windmill/scripts/platform-observation-loop.py`
- `platform/`
- `scripts/controller_automation_toolkit.py`
- `scripts/repo_package_loader.py`
- `scripts/session_workspace.py`
- `scripts/run_namespace.py`
- `scripts/parse_ansible_drift.py`
- `scripts/lv3_cli.py`
- `scripts/validate_dependency_direction.py`
- `scripts/validate_repo.sh`
- `tests/test_validate_dependency_direction.py`
- `tests/test_dependency_direction_gate.py`
- `tests/test_health_composite.py`
- `tests/test_lv3_cli.py`
- `receipts/live-applies/2026-03-28-adr-0208-dependency-direction-and-composition-roots-live-apply.json`

## Plan

- register the main-merge branch so workstream ownership validation can run from the clean integration worktree
- cut the `0.177.40` release and refresh the protected repo-version truth from the latest rebased `origin/main` candidate
- rerun the dependency-direction validator, focused ADR 0208 regression slice, repo validation gates, and the full `make validate` automation bundle before pushing `main`

## Result

- Release `0.177.40` integrates ADR 0208 into `main` without a platform-version bump; the repository-version fields advanced while `platform_version` remained `0.130.38`.
- The branch-local receipt `2026-03-28-adr-0208-dependency-direction-and-composition-roots-live-apply.json` remains the canonical live-apply evidence because this ADR is repository-only and did not require a separate merged-main platform replay receipt.
- The integrated validation pass succeeded for `python3 scripts/validate_dependency_direction.py --repo-root ...`, `./scripts/validate_repo.sh dependency-direction data-models architecture-fitness workstream-surfaces generated-docs agent-standards`, `./scripts/validate_repo.sh generated-portals`, `git diff --check`, and the focused ADR 0208 regression slice (`146 passed in 15.67s`).
- The full `make validate` automation bundle was exercised from this worktree before terminalizing the branch and exited nonzero only on eight pre-existing `ansible-lint` warnings in untouched collection roles under `collections/ansible_collections/lv3/platform/roles/`; no ADR 0208-owned surface failed that full-bundle run.
