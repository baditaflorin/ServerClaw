# Workstream ADR 0173: Workstream Surface Ownership Manifest

- ADR: [ADR 0173](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0173-workstream-surface-ownership-manifest.md)
- Title: Add machine-readable ownership manifests for active workstreams and enforce branch edits against them
- Status: implemented
- Implemented In Repo Version: 0.176.1
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Branch: `codex/adr-0173-ownership-manifest`
- Worktree: `../worktree-adr-0173-ownership-manifest`
- Owner: codex
- Depends On: `adr-0156-agent-session-workspace-isolation`, `adr-0172-watchdog-escalation`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/`, `scripts/validate_repo.sh`, `scripts/validate_repository_data_models.py`, `VERSION`, `changelog.md`, `versions/stack.yaml`

## Scope

- add an `ownership_manifest` to active workstream entries in `workstreams.yaml`
- define supported ownership modes and validate manifest structure
- reject branch edits that land outside declared mutable surfaces or touch generated/read-only surfaces directly
- seed manifests for the currently active workstreams so the rule is enforceable immediately
- document the manifest contract for future workstreams

## Non-Goals

- replacing runtime resource locking or live execution lanes
- auto-resolving path overlaps between arbitrary glob patterns
- migrating every historical workstream entry in the registry in the same cut

## Expected Repo Surfaces

- `scripts/workstream_surface_ownership.py`
- `scripts/generate_adr_index.py`
- `scripts/validate_repository_data_models.py`
- `scripts/validate_repo.sh`
- `tests/test_workstream_surface_ownership.py`
- `tests/test_validate_repo_cache.py`
- `workstreams.yaml`
- `docs/workstreams/README.md`
- `docs/workstreams/TEMPLATE.md`
- `docs/adr/0173-workstream-surface-ownership-manifest.md`
- `docs/workstreams/adr-0173-workstream-surface-ownership-manifest.md`

## Expected Live Surfaces

- none; this ADR is repository enforcement only

## Ownership Notes

- `workstreams.yaml` remains the machine-readable source of truth and uses `workstream-registry-v1` for shared registry updates
- the ownership validator script and tests are exclusive to this workstream
- release files are updated in this implementation cut because the user explicitly requested a version bump alongside the ADR landing

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_workstream_surface_ownership.py tests/test_validate_repo_cache.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml python scripts/workstream_surface_ownership.py --validate-registry`
- `uv run --with pyyaml python scripts/workstream_surface_ownership.py --validate-branch --base-ref origin/main`

## Merge Criteria

- active workstreams cannot omit an ownership manifest
- duplicate exclusive claims across active workstreams are rejected
- undeclared or generated branch edits are rejected for registered workstream branches
- the workstream docs explain how future branches declare ownership
