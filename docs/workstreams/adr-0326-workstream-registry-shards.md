# Workstream ws-0326-live-apply: ADR 0326 Workstream Registry Shards Live Apply

- ADR: [ADR 0326](../adr/0326-workstream-registry-shards-with-active-and-archive-assembly.md)
- Title: implement shard-backed workstream registry source files with generated active-only compatibility assembly
- Status: blocked
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0326-workstream-registry-shards-live-apply.json`
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Live Applied In Platform Version: N/A (repo-only control-plane change)
- Latest Verified Base: `origin/main@d36f1b1d92180aab4ec32e911e82d574338aa7fd` (`repo 0.178.1`, `platform 0.130.97`)
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

- The branch was created from latest `origin/main`, then rebased onto `origin/main@d36f1b1d92180aab4ec32e911e82d574338aa7fd` after `ws-0333-service-uptime-recovery` landed so the shard source also carries that newly archived workstream.
- The migration is now committed automation, not a one-off transform: `platform/workstream_registry.py` owns load, assemble, write, and migrate behavior; `scripts/workstream_registry.py` exposes the CLI; `scripts/canonical_truth.py`, `scripts/workstream_tool.py`, `scripts/generate_status_docs.py`, `scripts/generate_diagrams.py`, `scripts/drift_lib.py`, `scripts/workstream_surface_ownership.py`, `scripts/validate_repository_data_models.py`, and `scripts/validate_repo.sh` all consume the shard-backed source correctly.
- The compatibility artifact stays generated-only. After the rebase conflict on `workstreams.yaml`, the branch resolved it by importing the new `ws-0333-service-uptime-recovery` archive shard and regenerating `workstreams.yaml` from source, rather than hand-merging the generated file.
- Focused regression coverage passed on the rebased tree: `uv run --with pytest --with pyyaml python -m pytest tests/test_workstream_registry.py tests/test_canonical_truth.py tests/test_workstream_surface_ownership.py tests/test_interface_contracts.py -q` returned `27 passed in 2.97s`.
- `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-portals` passed on the rebased branch. The broader `generated-docs` lane was also exercised and failed only on the expected protected `changelog.md` canonical-truth delta that this branch is intentionally not allowed to write.
- `make remote-validate` exercised the live remote entrypoint and truthfully exposed two environmental follow-ups: the build server could not create a workspace in its managed workspace root because the host was out of space, so the run fell back locally; the fallback then surfaced a stale `build/platform-manifest.json`, which this branch refreshed and re-checked locally. The same fallback also hit an `ansible-syntax` timeout under the large concurrent validation load, so the remote replay is preserved as partial evidence rather than a clean pass.
- Final verification evidence is recorded in:
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-focused-tests-r1-0.178.1.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-validate-repo-r1-0.178.1.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-remote-validate-r1-0.178.1.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-generate-adr-index-r1-0.178.1.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-platform-manifest-write-r1-0.178.1.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-platform-manifest-check-r1-0.178.1.txt`,
  `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-git-diff-check-r1-0.178.1.txt`,
  and `receipts/live-applies/evidence/2026-04-03-ws-0326-mainline-live-apply-receipts-validate-r1-0.178.1.txt`.

## Outcome

- ADR 0326 is implemented on this rebased workstream branch, with authored workstream truth split into shard files and `workstreams.yaml` preserved as a generated active-only compatibility surface.
- The repo automation paths that depend on workstream metadata now validate the shard source directly or assemble the compatibility registry deterministically from it.
- The latest-main rebase proved that concurrent mainline changes can be absorbed safely by adding the new archived shard and regenerating `workstreams.yaml`, which is the intended operational model for this ADR.
- The branch now also carries the refreshed `build/platform-manifest.json` and diagram output needed to keep generated truth aligned with the shard-backed registry change set.

## Remaining Merge-To-Main

- This branch intentionally does not touch `VERSION`, release sections in `changelog.md`, the top-level `README.md` summary, or `versions/stack.yaml`.
- If this workstream becomes the exact `main` integration step, update the protected release bookkeeping on `main`: bump `VERSION`, refresh the changelog and any release-generated surfaces that depend on it, regenerate any affected truth artifacts, and then mark ADR 0326 as `Implemented` with its first integrated repo version.
- Because ADR 0326 changes repository coordination and validation structure rather than live infrastructure state, `versions/stack.yaml` and the platform version should remain unchanged unless a separate exact-main integration explicitly chooses to record this repo-only truth there.
- If a clean remote-gate proof is required before merging, first free space in the build host workspace root and rerun `make remote-validate`; the 2026-04-03 attempt fell back locally because remote workspace creation failed, and that fallback then timed out in `ansible-syntax` under concurrent validation load.
