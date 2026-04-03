# Workstream ws-0325-live-apply: Live Apply ADR 0325 From Latest `origin/main`

- ADR: [ADR 0325](../adr/0325-faceted-adr-index-shards-and-reservation-windows.md)
- Title: Live apply faceted ADR index shards and reservation windows from the latest `origin/main`
- Status: live_applied
- Included In Repo Version: `not yet`
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0325-adr-discovery-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-04-adr-0325-adr-discovery-mainline-live-apply.json`
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: not applicable (repo-only control-plane change)
- Latest Verified Base: `origin/main@6f0c993723e2706c9f6a5b3913d1c88ef70de52b` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0325-live-apply`
- Worktree: `.worktrees/ws-0325-live-apply`
- Owner: codex
- Depends On: `ADR 0164`, `ADR 0167`, `ADR 0168`, `ADR 0326`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0325-live-apply.yaml`, `docs/workstreams/ws-0325-live-apply.md`, `docs/adr/0325-faceted-adr-index-shards-and-reservation-windows.md`, `docs/adr/.index.yaml`, `docs/adr/index/`, `docs/runbooks/adr-discovery-and-reservations.md`, `.repo-structure.yaml`, `.config-locations.yaml`, `build/onboarding/*.yaml`, `docs/discovery/config-locations/agent-discovery.yaml`, `docs/discovery/repo-structure/automation-and-infrastructure.yaml`, `docs/discovery/repo-structure/documentation-and-history.yaml`, `config/validation-gate.json`, `config/validation-lanes.yaml`, `scripts/adr_discovery.py`, `scripts/generate_adr_index.py`, `scripts/adr_query_tool.py`, `scripts/generate_discovery_artifacts.py`, `scripts/validate_repo.sh`, `tests/test_generate_adr_index.py`, `tests/test_adr_query_tool.py`, `tests/test_generate_discovery_artifacts.py`, `tests/test_validation_lanes.py`, `README.md`, `changelog.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `receipts/live-applies/2026-04-03-adr-0325-adr-discovery-live-apply.json`, `receipts/live-applies/2026-04-04-adr-0325-adr-discovery-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-ws-0325-*`, `receipts/live-applies/evidence/2026-04-04-ws-0325-*`

## Scope

- replace the monolithic ADR discovery catalog with a compact root manifest plus
  range, concern, and implementation-status shards under `docs/adr/index/`
- add a committed reservation ledger and reservation-aware ADR allocation/query
  workflow
- extend the repo validation and discovery generation paths so stale ADR and
  generated discovery surfaces fail cleanly, including UTC-stable generated
  dates across the Bucharest controller and UTC build hosts
- replay the exact-main integration onto the latest `origin/main` without
  cutting a blocked numbered repo release

## Outcome

- `scripts/adr_discovery.py`, `scripts/generate_adr_index.py`, and
  `scripts/adr_query_tool.py` now support shard-backed ADR discovery plus
  reservation-aware allocation without relying on hidden chat coordination.
- `docs/adr/.index.yaml` now points readers at shard-sized metadata surfaces,
  and the rebased replay preserves the latest `origin/main` ADR additions
  (`0342`-`0345`) inside the shard outputs instead of regressing to the old
  monolithic index.
- `scripts/generate_discovery_artifacts.py` and `scripts/generate_adr_index.py`
  now stamp generated dates in UTC, which keeps exact-main validation stable
  when the controller and build host cross midnight in different time zones.
- Repo automation now fails closed on stale ADR shards, stale generated
  discovery entrypoints, and drift in the exact-main workstream ownership
  contract.

## Verification

- Focused regression coverage passed on the rebased exact-main tree: `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_generate_adr_index.py tests/test_adr_query_tool.py tests/test_validation_lanes.py tests/test_workstream_registry.py tests/test_generate_discovery_artifacts.py`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0325-mainline-targeted-tests-r1.txt`.
- Generated-surface drift checks passed after the rebase onto `origin/main@6f0c993723e2706c9f6a5b3913d1c88ef70de52b`: `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`, `./scripts/run_python_with_packages.sh pyyaml -- scripts/generate_adr_index.py --check`, `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`, and `git diff --check`, preserved in the matching `2026-04-04-ws-0325-mainline-*.txt` evidence files.
- Release bookkeeping remains intentionally unreleased: `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py status --json` still reports repository version `0.178.3`, platform version `0.130.98`, and a blocked release cut because three unrelated `controller_dependency_gap` waiver receipts remain open through `2026-04-06`; the next candidate repo version remains `0.178.4`, preserved in `receipts/live-applies/evidence/2026-04-04-ws-0325-mainline-release-status-r1.json` and `receipts/live-applies/evidence/2026-04-04-ws-0325-mainline-release-dry-run-r1.txt`.
- `python3 scripts/live_apply_receipts.py --validate`, `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models generated-docs generated-portals`, `make remote-validate`, and `make pre-push-gate` passed on the rebased exact-main tree; the remote build still needed the usual unresolved-only local fallback for `atlas-lint`, and that fallback passed and merged cleanly into the recorded gate status.

## Exact-Main Integration Status

- The exact-main integration is complete on the latest `origin/main`, with the
  shard-backed ADR discovery rollout, reservation ledger, and generated
  discovery entrypoints refreshed from source rather than hand-merged.
- `VERSION` remains `0.178.3` and `Implemented In Repo Version` remains `not yet`
  because the release manager still blocks a fresh numbered cut on unrelated
  open waiver receipts outside this workstream.
- Because ADR 0325 is a repo-only control-plane change, no platform version bump
  should accompany the merge; the live platform version context remains
  `0.130.98`.
