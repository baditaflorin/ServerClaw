# Workstream ws-0337-live-apply: ADR 0337 Fork-First Metadata Closeout

- ADR: [ADR 0337](../adr/0337-fork-first-workstream-and-worktree-metadata.md)
- Title: re-verify fork-first workstream and worktree metadata from latest origin/main
- Status: live_applied
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0337-fork-first-workstream-metadata-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0337-fork-first-workstream-metadata-mainline-live-apply.json`
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: not applicable (repo-only metadata change)
- Latest Verified Base: `origin/main@20a66bbf0` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0337-live-apply`
- Worktree: `.worktrees/ws-0337-live-apply`
- Owner: codex
- Depends On: `ADR 0167`, `ADR 0326`, `ADR 0331`, `ADR 0337`
- Conflicts With: none
- Shared Surfaces: `workstreams/policy.yaml`, `workstreams/active/*.yaml`, `workstreams/archive/**/*.yaml`, `workstreams.yaml`, `docs/workstreams/ws-0337-live-apply.md`, `docs/adr/0337-fork-first-workstream-and-worktree-metadata.md`, `docs/adr/.index.yaml`, `docs/adr/index/**/*.yaml`, `docs/runbooks/workstream-registry-shards.md`, `docs/status/history/merged-workstreams.md`, `platform/repo.py`, `scripts/create-workstream.sh`, `scripts/scaffold_service.py`, `scripts/validate_public_entrypoints.py`, `scripts/validate_repository_data_models.py`, `scripts/workstream_surface_ownership.py`, `tests/test_scaffold_service.py`, `tests/test_validate_public_entrypoints.py`, `tests/test_workstream_surface_ownership.py`, `receipts/live-applies/2026-04-04-adr-0337-fork-first-workstream-metadata-live-apply.json`, `receipts/live-applies/2026-04-04-adr-0337-fork-first-workstream-metadata-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-04-ws-0337-*`

## Scope

- close the gap between ADR 0337's repository-relative contract and the legacy
  shard entries that still pointed outside the repo root with `../...`
- normalize workstream `doc` metadata back to the canonical in-repo `docs/...`
  paths instead of another worktree's nested copy
- make the worktree helper and the service scaffold keep emitting repo-local
  metadata instead of recreating parent-relative paths in new workstreams
- re-run the repository automation and validation surfaces from an exact-main
  worktree so the portability contract is proven on the current realistic base

## Verification

- `python3 scripts/validate_public_entrypoints.py --check` initially failed on
  exact main because `workstreams.yaml` still exposed out-of-repo `worktree_path`
  and `doc` values; the final tree re-ran that check green after the shard
  normalization.
- The final exact-main tree is validated through `scripts/workstream_registry.py
  --write`, `scripts/workstream_registry.py --check`, `./scripts/validate_repo.sh
  agent-standards`, `./scripts/validate_repo.sh workstream-surfaces`, `uv run
  --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py
  --validate`, focused pytest coverage for the public-entrypoint and workstream
  ownership checks, and `git diff --check`.
- The live-apply evidence is repository-only: no platform mutation was required,
  so the receipt records the exact-main validation pass and the metadata
  normalization instead of a guest or service replay.

## Outcome

- the shard-backed workstream registry now keeps committed `worktree_path`
  metadata under repo-local `.worktrees/<workstream-id>` paths instead of legacy
  parent-relative locations
- workstream `doc` metadata now points at canonical `docs/workstreams/...` files
  rather than nested copies inside another worktree
- `scripts/create-workstream.sh` now refuses metadata that would resolve outside
  the repository, and `scripts/scaffold_service.py` plus its tests preserve the
  `.worktrees/<workstream-id>` and `docs/workstreams/...` conventions for new
  service scaffolds
- ADR 0337 now matches current exact-main truth, and future drift is blocked by
  the same repository-relative validation already wired into the repo gate

## Exact-Main Integration Status

- this workstream is intended to merge onto `main` without a release cut, so
  `Included In Repo Version` remains `not yet`
- `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml` remain
  untouched in this workstream because the change is repository-only portability
  hardening rather than a numbered release or platform-state update
