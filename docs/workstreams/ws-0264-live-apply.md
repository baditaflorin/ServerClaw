# Workstream WS-0264: Failure-Domain-Isolated Validation Lanes Live Apply

- ADR: [ADR 0264](../adr/0264-failure-domain-isolated-validation-lanes.md)
- Title: Partition the repository validation gate into failure-domain-isolated lanes and verify the build-server plus worker automation end to end
- Status: in_progress
- Branch: `codex/adr-0264-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0264-live-apply`
- Owner: codex
- Depends On: `ws-0264-receipt-driven-resilience-adrs`, `adr-0087-validation-gate`, `adr-0167-workstream-handoff-protocol`, `adr-0173-workstream-surface-ownership-manifest`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0264-failure-domain-isolated-validation-lanes.md`, `docs/workstreams/ws-0264-live-apply.md`, `docs/runbooks/validation-gate.md`, `.config-locations.yaml`, `config/build-server.json`, `config/validation-gate.json`, `config/workflow-catalog.json`, `docs/diagrams/agent-coordination-map.excalidraw`, `scripts/parallel_check.py`, `scripts/remote_exec.sh`, `scripts/run_gate.py`, `scripts/gate_status.py`, `scripts/run_python_with_packages.sh`, `scripts/validate_repo.sh`, `scripts/workstream_surface_ownership.py`, `tests/test_parallel_check.py`, `tests/test_validate_repo_cache.py`, `tests/test_validation_gate.py`, `tests/test_validation_gate_windmill.py`, `tests/test_workstream_surface_ownership.py`, `workstreams.yaml`
- Ownership Manifest: `workstreams.yaml` `ownership_manifest`

## Scope

- implement the ADR 0264 lane model on top of the existing manifest-driven validation gate
- keep a small fast set of global invariants blocking while unrelated heavy checks become non-blocking by default for focused changes
- emit reusable lane-level evidence summaries in the recorded gate status payloads
- verify the lane-aware gate locally, on the remote build server, and through the worker-side post-merge entrypoint

## Non-Goals

- implementing the neighboring ADR 0265 through ADR 0273 surfaces in the same workstream
- changing protected release files before the final merge-to-main step
- weakening the existing validation coverage for broad or integration-heavy changes

## Expected Repo Surfaces

- `docs/adr/0264-failure-domain-isolated-validation-lanes.md`
- `docs/workstreams/ws-0264-live-apply.md`
- `docs/runbooks/validation-gate.md`
- `.config-locations.yaml`
- `docs/adr/.index.yaml`
- `config/build-server.json`
- `config/validation-gate.json`
- `config/validation-lanes.yaml`
- `config/workflow-catalog.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `scripts/parallel_check.py`
- `scripts/run_gate.py`
- `scripts/remote_exec.sh`
- `scripts/run_python_with_packages.sh`
- `scripts/gate_status.py`
- `scripts/validate_repo.sh`
- `scripts/validation_lanes.py`
- `scripts/workstream_surface_ownership.py`
- `config/windmill/scripts/post-merge-gate.py`
- `config/windmill/scripts/gate-status.py`
- `tests/test_parallel_check.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_gate_windmill.py`
- `tests/test_validation_lanes.py`
- `tests/test_validate_repo_cache.py`
- `tests/test_workstream_surface_ownership.py`
- `workstreams.yaml`

## Expected Live Surfaces

- `make pre-push-gate` on the latest isolated worktree resolves lane scope from changed surfaces and records lane-level status payloads
- the remote build-server gate blocks only the lanes owned by the current change plus the fast global invariants
- the worker-side post-merge gate and status wrapper understand the same lane metadata and recorded evidence

## Ownership Notes

- this workstream owns the validation-lane catalog, gate runner, lane status formatting, and the corresponding runbook and tests
- protected integration files stay untouched on this branch unless and until the workstream is merged and re-verified from `main`

## Verification

- `uv run --with pytest python -m pytest tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_validation_lanes.py -q`
- `./scripts/validate_repo.sh data-models workstream-surfaces agent-standards`
- `make pre-push-gate`
- `make gate-status`
- `make post-merge-gate`

## Merge Criteria

- focused docs-only or ADR-only changes no longer hard-block on unrelated builder or service lanes by default
- lane selection is derived from committed repo metadata instead of ad hoc command-line conventions
- gate status payloads show which lanes were selected, which checks blocked, and the reusable green-path summaries for passed lanes

## Notes For The Next Assistant

- keep lane selection conservative: when a changed surface is unknown, widen to all lanes instead of silently skipping protection
- preserve explicit evidence for both the build-server path and the worker fallback path because ADR 0264 is about trustworthy validation boundaries, not just faster pushes
