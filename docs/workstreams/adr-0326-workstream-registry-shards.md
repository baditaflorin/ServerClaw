# Workstream ws-0326-live-apply: ADR 0326 Workstream Registry Shards Live Apply

- ADR: [ADR 0326](../adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md)
- Title: implement shard-backed workstream registry source files with generated active-only compatibility assembly
- Status: in_progress
- Branch: `codex/ws-0326-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0326-live-apply`
- Owner: codex
- Depends On: `ADR 0167`, `ADR 0174`, `ADR 0175`, `ADR 0326`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/policy.yaml`, `workstreams/active/*.yaml`, `workstreams/archive/*.yaml`, `platform/workstream_registry.py`, `scripts/workstream_registry.py`, `scripts/workstream_tool.py`, `scripts/create-workstream.sh`, `scripts/canonical_truth.py`, `scripts/generate_status_docs.py`, `scripts/generate_diagrams.py`, `scripts/drift_lib.py`, `scripts/workstream_surface_ownership.py`, `scripts/validate_repository_data_models.py`, `scripts/validate_repo.sh`, `docs/adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md`, `docs/runbooks/workstream-registry-shards.md`, `docs/runbooks/cross-workstream-interface-contracts.md`, `docs/runbooks/canonical-truth-assembly.md`, `docs/runbooks/validate-repository-automation.md`, `.repo-structure.yaml`, `.config-locations.yaml`, `config/contracts/workstream-registry-v1.yaml`, `tests/test_workstream_registry.py`, `tests/test_canonical_truth.py`, `tests/test_workstream_surface_ownership.py`, `tests/test_interface_contracts.py`

## Scope

- move authored workstream metadata into `workstreams/policy.yaml`, `workstreams/active/`, and `workstreams/archive/`
- keep `workstreams.yaml` as a generated compatibility artifact for current callers and onboarding
- update repo automation so release management, generated docs, branch ownership checks, and workstream helpers operate correctly with the new source layout
- validate the shard workflow locally and through the live repo automation path before integration

## Verification Plan

- migrate the current registry from latest `origin/main` into shard files with committed tooling rather than ad hoc edits
- register this workstream in the new active shard source and regenerate `workstreams.yaml`
- run focused unit tests for the registry loader, canonical-truth release bookkeeping, and ownership validation
- run `scripts/validate_repo.sh agent-standards data-models generated-docs workstream-surfaces`
- replay at least one live repo-validation path that consumes the compatibility artifact from a fresh exact-main worktree or server-resident runner

## Merge Notes

- `VERSION`, release sections in `changelog.md`, the top-level `README.md` status summary, and `versions/stack.yaml` stay untouched on this branch unless this workstream becomes the final main integration step
- if the live apply completes before shared release surfaces are integrated on `main`, record the exact remaining merge-to-main steps in this document and the receipt
