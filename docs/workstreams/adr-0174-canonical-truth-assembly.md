# Workstream ADR 0174: Integration-Only Canonical Truth Assembly

- ADR: [ADR 0174](../adr/0174-integration-only-canonical-truth-assembly.md)
- Title: assemble integration-only canonical truth from workstream metadata and keep live apply gated on current integrated files
- Status: merged
- Branch: `codex/adr-0174-canonical-truth`
- Worktree: `../worktree-adr-0174-canonical-truth`
- Owner: codex
- Depends On: `adr-0110-platform-versioning`
- Conflicts With: none
- Shared Surfaces: `scripts/canonical_truth.py`, `scripts/release_manager.py`, `scripts/generate_status_docs.py`, `scripts/validate_repository_data_models.py`, `Makefile`, `scripts/validate_repo.sh`, `docs/runbooks/canonical-truth-assembly.md`

## Scope

- add a repo-managed assembler for `README.md`, `VERSION`-aligned `versions/stack.yaml` fields, and `changelog.md`
- add structured `canonical_truth` metadata on workstreams so release notes and latest live-apply receipt mappings can be derived from branch-local state
- make release generation consume the assembled `## Unreleased` notes instead of relying on manual edits
- fail live apply early when the integration-only files are stale

## Non-Goals

- moving the entire desired-state body of `versions/stack.yaml` into fragments in one turn
- auto-merging feature branches onto `main`
- claiming a platform version bump without a verified live apply from `main`

## Expected Repo Surfaces

- `scripts/canonical_truth.py`
- `scripts/release_manager.py`
- `scripts/validate_repository_data_models.py`
- `tests/test_canonical_truth.py`
- `Makefile`
- `scripts/validate_repo.sh`
- `docs/runbooks/canonical-truth-assembly.md`
- `docs/workstreams/adr-0174-canonical-truth-assembly.md`

## Expected Live Surfaces

- `make live-apply-service ...`, `make live-apply-group ...`, and `make live-apply-site ...` refuse to run when canonical truth is stale
- release preparation can regenerate top-level canonical truth directly from the integrated workstream registry before the release tag is cut

## Verification

- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_canonical_truth.py tests/test_release_manager.py`
- `uvx --from pyyaml python scripts/canonical_truth.py --check`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- workstream-local release metadata can render `changelog.md` unreleased notes without manual edits
- `versions/stack.yaml` repo-version fields and declared latest receipt mappings are assembled deterministically
- the release manager can cut a release from assembled notes and mark the contributing workstreams as released
- live-apply entrypoints reject stale integration-only canonical truth

## Outcome

- repository implementation is complete on `main` in repo release `0.176.3`
- no live platform version change is claimed; this workstream governs integration and release automation only
