# Workstream ADR 0182: Live Apply Merge Train and Rollback Bundle

- ADR: [ADR 0182](../adr/0182-live-apply-merge-train-and-rollback-bundle.md)
- Title: Batch ready workstreams into a reviewed live-apply train, serialize shared surfaces into waves, and require an executable rollback bundle before mutation begins
- Status: merged
- Branch: `codex/adr-0182-live-apply-landing`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-adr-0182-live-apply-landing`
- Owner: codex
- Depends On: `adr-0155-intent-queue-with-release-triggered-scheduling`, `adr-0173-workstream-surface-ownership-manifest`, `adr-0178-dependency-wave-manifests-for-parallel-apply`
- Conflicts With: none
- Shared Surfaces: `platform/live_apply/`, `scripts/live_apply_merge_train.py`, `Makefile`, `scripts/validate_repository_data_models.py`, `docs/runbooks/live-apply-merge-train.md`

## Scope

- add a repo-managed merge-train queue and planner
- require train-eligible workstreams to declare live-apply metadata in `workstreams.yaml`
- build rollback bundles before merge-train execution
- revert merged branches automatically when an apply step fails
- document the operator flow and add focused regression coverage

## Non-Goals

- background daemons that auto-run merge trains without an operator trigger
- true concurrent execution inside one wave
- automatic editing of other workstreams to make them train-ready
- claiming a new live platform version from this repo-only implementation

## Expected Repo Surfaces

- `platform/live_apply/__init__.py`
- `platform/live_apply/merge_train.py`
- `scripts/live_apply_merge_train.py`
- `scripts/validate_repository_data_models.py`
- `Makefile`
- `tests/unit/test_live_apply_merge_train.py`
- `docs/runbooks/live-apply-merge-train.md`
- `docs/adr/0182-live-apply-merge-train-and-rollback-bundle.md`
- `docs/workstreams/adr-0182-live-apply-merge-train-and-rollback-bundle.md`

## Expected Live Surfaces

- operators can queue train-eligible workstreams
- the planner batches disjoint workstreams into one wave and serializes shared surfaces
- a rollback bundle is written before merges or live-apply steps begin
- failed apply steps trigger bundle execution and revert merged branches

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/unit/test_live_apply_merge_train.py -q`
- `python3 -m py_compile platform/live_apply/merge_train.py scripts/live_apply_merge_train.py scripts/validate_repository_data_models.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- train admission rejects workstreams without docs, checks, apply waves, and rollback steps
- shared surfaces serialize in the plan while disjoint workstreams stay in the same wave
- rollback bundles capture file snapshots before mutation
- a failed apply restores pre-train runtime state and reverts merge commits

## Outcome

- merged in repo version `0.176.6`
- live platform apply not yet performed from `main`
