# Workstream ws-0208-live-apply: Dependency Direction And Composition Roots

- ADR: [ADR 0208](../adr/0208-dependency-direction-and-composition-roots.md)
- Title: enforce inward dependency direction for reusable `platform/` code and move runtime wiring to explicit composition roots
- Status: live_applied
- Implemented In Repo Version: 0.177.40
- Implemented In Platform Version: not applicable (repository-only)
- Implemented On: 2026-03-28
- Branch: `codex/ws-0208-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0208-live-apply`
- Owner: codex
- Depends On: `adr-0204-architecture-governance`, `adr-0206-ports-and-adapters-for-external-integrations`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/adr/0208-dependency-direction-and-composition-roots.md`, `docs/workstreams/ws-0208-live-apply.md`, `docs/runbooks/validate-repository-automation.md`, `docs/adr/.index.yaml`, `config/validation-gate.json`, `Makefile`, `scripts/validate_repo.sh`, `scripts/validate_dependency_direction.py`, `platform/`

## Scope

- remove outward imports from reusable `platform/` modules into `scripts/` and
  script-like top-level helpers
- move shared helper logic inward under `platform/` so delivery/runtime code can
  import shared utilities without inverting the dependency direction
- make composition roots explicit by having `scripts/lv3_cli.py` and
  `config/windmill/scripts/platform-observation-loop.py` pass the incident
  triage builder into `ClosureLoop`
- add an ADR 0208 dependency-direction validator to the local validation
  wrapper, the remote validation gate manifest, and a dedicated `make`
  target
- capture repository-only live-apply evidence and complete the mainline repo
  version, changelog, and release-note integration without changing the
  platform version

## Non-Goals

- reorganizing the whole repository into new top-level directories in one cut
- banning script entrypoints or shell wrappers that are themselves composition
  roots
- updating protected integration files on this workstream branch

## Expected Repo Surfaces

- `platform/repo.py`
- `platform/catalogs.py`
- `platform/package_loader.py`
- `platform/session_workspace.py`
- `platform/run_namespace.py`
- `platform/ansible_drift.py`
- `platform/events/`
- `platform/correction_loops.py`
- `platform/mutation_audit.py`
- `platform/maintenance/`
- `platform/slo.py`
- `platform/health/composite.py`
- `platform/world_state/workers.py`
- `platform/closure_loop/engine.py`
- `platform/agent/`
- `platform/config_merge/registry.py`
- `platform/ledger/`
- `platform/scheduler/watchdog.py`
- `platform/diff_engine/`
- `platform/goal_compiler/compiler.py`
- `platform/interface_contracts.py`
- `platform/graph/client.py`
- `platform/live_apply/merge_train.py`
- `platform/use_cases/runbooks.py`
- `scripts/controller_automation_toolkit.py`
- `scripts/repo_package_loader.py`
- `scripts/session_workspace.py`
- `scripts/run_namespace.py`
- `scripts/parse_ansible_drift.py`
- `scripts/lv3_cli.py`
- `scripts/validate_dependency_direction.py`
- `scripts/validate_repo.sh`
- `config/validation-gate.json`
- `Makefile`
- `tests/test_validate_dependency_direction.py`
- `tests/test_dependency_direction_gate.py`
- `tests/test_correction_loops.py`

## Expected Live Surfaces

- none; this ADR is a repository-only live rollout

## Ownership Notes

- reusable `platform/` code now owns the shared helpers for repository reads,
  catalogs, maintenance windows, SLO queries, session workspaces, run
  namespaces, Ansible drift parsing, correction-loop resolution, mutation-audit
  emission, and NATS publishing
- the CLI and Windmill observation-loop wrapper are the composition roots that
  now inject the incident-triage builder into `ClosureLoop`
- the final `main` integration released ADR 0208 in repo version `0.177.40`
  and updated `VERSION`, `changelog.md`, release notes, `README.md`, and the
  repository-version fields in `versions/stack.yaml` while leaving
  `platform_version` unchanged at `0.130.38`

## Verification

- `python3 scripts/validate_dependency_direction.py --repo-root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0208-live-apply`
- `make validate-dependency-direction`
- `./scripts/validate_repo.sh dependency-direction agent-standards`
- `UV_CACHE_DIR=/tmp/uv-cache uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_validate_dependency_direction.py tests/test_dependency_direction_gate.py tests/test_correction_loops.py tests/test_runbook_executor.py tests/test_api_gateway.py tests/test_run_namespace.py tests/test_session_workspace.py tests/test_parse_ansible_drift.py tests/test_slo_tracking.py tests/unit/test_closure_loop.py tests/test_health_composite.py tests/test_world_state_workers.py tests/test_lv3_cli.py tests/test_ansible_execution_scopes.py tests/test_interface_contracts.py tests/test_platform_llm_client.py tests/unit/test_diff_engine.py tests/unit/test_goal_compiler.py -q`

## Merge Criteria

- reusable `platform/` modules no longer import outward into `scripts/`
- the ADR 0208 validator blocks regressions in both `scripts/validate_repo.sh`
  and `config/validation-gate.json`
- the branch-local receipt records the repository-only rollout and explicitly
  lists the protected integration follow-up for `main`

## Outcome

- reusable helper logic now lives under `platform/`, and the affected platform
  services no longer depend on `scripts/` imports or script-file dynamic loads
- the ADR 0208 validator now gates regressions through `scripts/validate_repo.sh`,
  `config/validation-gate.json`, and the dedicated `make validate-dependency-direction`
  target
- repository version `0.177.40` integrated the workstream into `main` without a
  platform-version bump because the rollout is repository-only
- the branch-local receipt remains the canonical live-apply evidence; no
  separate platform replay receipt was required for the `main` integration

## Notes For The Next Assistant

- if another workstream needs to touch `scripts/lv3_cli.py`, `Makefile`, or the
  validation gate manifest before this branch lands, refresh from the latest
  `origin/main` first and keep the ADR 0208 validator entry intact
- future work on these surfaces should preserve the composition-root wiring and
  the inward dependency rule; ADR 0208 itself has no remaining mainline truth
  updates pending
