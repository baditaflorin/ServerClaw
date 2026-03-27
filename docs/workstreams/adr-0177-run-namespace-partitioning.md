# Workstream ADR 0177: Run Namespace Partitioning

- ADR: [ADR 0177](../adr/0177-run-namespace-partitioning-for-parallel-tooling.md)
- Title: Run-scoped local scratch paths for parallel live-apply, dry-run, and OpenTofu tooling
- Status: merged
- Branch: `codex/adr-0177-namespace-partitioning`
- Worktree: `../worktree-adr-0177-namespace-partitioning`
- Owner: codex
- Depends On: `adr-0156-agent-session-workspace-isolation`, `adr-0160-parallel-dry-run-fan-out`
- Conflicts With: none
- Shared Surfaces: `Makefile`, `scripts/run_namespace.py`, `scripts/run_with_namespace.sh`, `scripts/tofu_exec.sh`, `scripts/remote_exec.sh`, `platform/diff_engine/adapters/`, `scripts/drift_detector.py`, `docs/runbooks/run-namespace-partitioning.md`

## Scope

- add a canonical resolver for `.local/runs/<run_id>/...`
- route Ansible temp, retry, control-path, and log outputs through the run namespace
- route OpenTofu plan and runtime copies through the run namespace
- forward `LV3_RUN_ID` through the remote execution gateway
- cover concurrent partitioned execution in focused tests
- document operator usage for repeated `plan`/`apply` flows that must reuse the same `RUN_ID`

## Non-Goals

- changing canonical committed receipt publication paths
- adding an automatic garbage collector for old run namespaces
- performing a live platform apply from `main`

## Expected Repo Surfaces

- `Makefile`
- `scripts/run_namespace.py`
- `scripts/run_with_namespace.sh`
- `scripts/tofu_exec.sh`
- `scripts/remote_exec.sh`
- `platform/diff_engine/adapters/ansible_adapter.py`
- `platform/diff_engine/adapters/opentofu_adapter.py`
- `scripts/drift_detector.py`
- `tests/test_run_namespace.py`
- `tests/test_drift_detector.py`
- `tests/test_remote_exec.py`
- `tests/unit/test_diff_engine.py`
- `docs/adr/0177-run-namespace-partitioning-for-parallel-tooling.md`
- `docs/runbooks/run-namespace-partitioning.md`
- `docs/workstreams/adr-0177-run-namespace-partitioning.md`

## Expected Live Surfaces

- separate worktrees can launch `make live-apply-*` without sharing controller-local Ansible temp or log paths
- parallel diff-engine fan-out uses one OpenTofu plan directory per run instead of `~/.cache/lv3-tofu-plans`
- remote OpenTofu commands can reuse a plan namespace by repeating the same `RUN_ID`

## Verification

- `bash -n scripts/tofu_exec.sh scripts/remote_exec.sh`
- `python3 -m py_compile scripts/run_namespace.py scripts/session_workspace.py scripts/drift_detector.py platform/diff_engine/adapters/ansible_adapter.py platform/diff_engine/adapters/opentofu_adapter.py scripts/tofu_remote_command.py`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_run_namespace.py tests/test_session_workspace.py tests/test_drift_detector.py tests/test_remote_exec.py tests/unit/test_diff_engine.py -q`
- `make -n live-apply-service service=api-gateway env=production EXTRA_ARGS='--check'`
- `make -n validate-tofu`

## Merge Criteria

- mutable controller-local Ansible artifacts are written under `.local/runs/<run_id>/ansible/` and `.local/runs/<run_id>/logs/`
- OpenTofu plans and runtime copies are written under `.local/runs/<run_id>/tofu/`
- nested remote tooling receives the caller's `LV3_RUN_ID`
- focused tests prove concurrent OpenTofu diff runs use distinct namespaces

## Outcome

- merged in repo version `0.175.3`
- live apply not yet performed from `main`

## Notes For The Next Assistant

- reuse the same `RUN_ID` when a manual OpenTofu `plan` must be followed by `apply` against the saved plan bundle
