# Workstream ws-0326-live-apply: ADR 0326 Workstream Registry Shards Live Apply

- ADR: [ADR 0326](../adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md)
- Title: implement shard-backed workstream registry source files with generated active-only compatibility assembly
- Status: ready_for_merge
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0326-workstream-registry-shards-live-apply.json`
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Live Applied In Platform Version: N/A (repo-only control-plane change)
- Latest Verified Base: `origin/main@6b9117310ef45ccc8e08855f33b4ddeeb746e4ee` (`repo 0.178.2`, `platform 0.130.98`)
- Branch: `codex/ws-0326-live-apply`
- Worktree: `.worktrees/ws-0326-live-apply`
- Owner: codex
- Depends On: `ADR 0167`, `ADR 0174`, `ADR 0175`, `ADR 0326`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/policy.yaml`, `workstreams/active/*.yaml`, `workstreams/archive/*.yaml`, `platform/workstream_registry.py`, `scripts/workstream_registry.py`, `scripts/workstream_tool.py`, `scripts/create-workstream.sh`, `scripts/canonical_truth.py`, `scripts/generate_status_docs.py`, `scripts/generate_diagrams.py`, `scripts/drift_lib.py`, `scripts/workstream_surface_ownership.py`, `scripts/validate_repository_data_models.py`, `scripts/validate_repo.sh`, `docs/adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md`, `docs/runbooks/workstream-registry-shards.md`, `docs/runbooks/cross-workstream-interface-contracts.md`, `docs/runbooks/canonical-truth-assembly.md`, `docs/runbooks/validate-repository-automation.md`, `.repo-structure.yaml`, `.config-locations.yaml`, `config/contracts/workstream-registry-v1.yaml`, `tests/test_workstream_registry.py`, `tests/test_canonical_truth.py`, `tests/test_workstream_surface_ownership.py`, `tests/test_interface_contracts.py`, `docs/diagrams/agent-coordination-map.excalidraw`, `build/platform-manifest.json`, `receipts/live-applies/2026-04-03-adr-0326-workstream-registry-shards-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-ws-0326-*`

## Scope

- move authored workstream metadata into `workstreams/policy.yaml`, `workstreams/active/`, and `workstreams/archive/`
- keep `workstreams.yaml` as a generated compatibility artifact for current callers and onboarding
- update repo automation so release management, generated docs, branch ownership checks, and workstream helpers operate correctly with the new source layout
- validate the shard workflow locally and through the live repo automation path before integration

## Verification

- The branch was rebased onto `origin/main@387dadb451507490cf584fe24af5792577bff9d2` while resolving the shard migration conflict by importing the newly merged `ws-0332-homepage-triage` archive shard and regenerating `workstreams.yaml` from shard source instead of hand-merging the generated registry. The branch also retains the earlier `ws-0333-service-uptime-recovery` archive shard from the prior replay.
- The migration is committed automation, not a one-off transform: `platform/workstream_registry.py` owns load, assemble, write, and migrate behavior; `scripts/workstream_registry.py` exposes the CLI; `scripts/canonical_truth.py`, `scripts/workstream_tool.py`, `scripts/generate_status_docs.py`, `scripts/generate_diagrams.py`, `scripts/drift_lib.py`, `scripts/workstream_surface_ownership.py`, `scripts/validate_repository_data_models.py`, and `scripts/validate_repo.sh` all consume the shard-backed source correctly.
- Focused regression coverage passed on the repaired tree: `uv run --with pytest --with pyyaml python -m pytest tests/test_workstream_registry.py tests/test_canonical_truth.py tests/test_workstream_surface_ownership.py tests/test_interface_contracts.py -q` returned `27 passed in 2.79s`.
- `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-portals` passed on the final metadata state and exercised the shard-backed registry, ownership surfaces, schema bundle, and generated portal build without touching the protected release files reserved for exact-main integration.
- The build-host workspace cleanup recorded in `receipts/live-applies/evidence/2026-04-03-ws-0326-build-host-workspace-cleanup-r1-0.178.1.txt` recovered the remote builder from disk exhaustion by pruning 44 stale session roots and increasing free space from `108G` to `119G`.
- A first post-rebase `make remote-validate` replay proved the remote path could start again and then exposed two stale generated surfaces on the branch, `build/platform-manifest.json` and `docs/diagrams/agent-coordination-map.excalidraw`. Both were regenerated and re-checked locally before the second replay.
- A repaired `make remote-validate` replay passed end to end against `origin/main@6b9117310ef45ccc8e08855f33b4ddeeb746e4ee` with all blocking checks green, and a final replay after the receipt/workstream refresh passed again on the commit-ready tree. Those runs preserved the protected `VERSION`, `changelog.md`, top-level `README.md` summary, and `versions/stack.yaml` updates for the later exact-main integration step.
- Final verification evidence is recorded in `receipts/live-applies/evidence/2026-04-03-ws-0326-build-host-workspace-cleanup-r1-0.178.1.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0326-targeted-tests-post-rebase-r1-0.178.2.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0326-validate-repo-post-rebase-r3-0.178.2.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0326-remote-validate-post-rebase-r1-0.178.2.txt`, `receipts/live-applies/evidence/2026-04-03-ws-0326-remote-validate-post-rebase-r2-0.178.2.txt`, and `receipts/live-applies/evidence/2026-04-03-ws-0326-remote-validate-post-rebase-r3-0.178.2.txt`.

## Outcome

- ADR 0326 is implemented on this rebased workstream branch, with authored workstream truth split into shard files and `workstreams.yaml` preserved as a generated active-only compatibility surface.
- The repo automation paths that depend on workstream metadata now validate the shard source directly or assemble the compatibility registry deterministically from it.
- The latest-main replay proved that concurrent mainline changes can be absorbed safely by adding new archived shards and regenerating `workstreams.yaml`, which is the intended operational model for this ADR.
- The branch now also carries the refreshed `build/platform-manifest.json` and diagram output needed to keep generated truth aligned with both the shard-backed registry change set and the newer exact-main validation base.

## Remaining Merge-To-Main

- This branch intentionally does not touch `VERSION`, release sections in `changelog.md`, the top-level `README.md` summary, or `versions/stack.yaml`.
- `origin/main` advanced again to `6b9117310ef45ccc8e08855f33b4ddeeb746e4ee` during the post-rebase verification pass, so exact-main integration should begin with one fresh fetch/rebase and a replay of `workstreams.yaml`, `build/platform-manifest.json`, and `docs/diagrams/agent-coordination-map.excalidraw`.
- On the exact-main integration step only, update the protected release bookkeeping on `main`: bump `VERSION`, refresh the changelog and any release-generated surfaces that depend on it, and then promote ADR 0326 from `Implemented on workstream branch` to `Implemented` with its first integrated repo version.
- Because ADR 0326 changes repository coordination and validation structure rather than live infrastructure state, `versions/stack.yaml` and the platform version should remain unchanged unless a separate exact-main integration explicitly chooses to record this repo-only truth there.
