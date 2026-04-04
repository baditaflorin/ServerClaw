# Workstream ws-0327-live-apply: ADR 0327 Sectional Discovery Live Apply

- ADR: [ADR 0327](../adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md)
- Title: sectional agent discovery registries and generated onboarding packs
- Status: live_applied
- Included In Repo Version: 0.178.4
- Branch-Local Receipt: `receipts/live-applies/2026-04-03-adr-0327-sectional-agent-discovery-live-apply.json`
- Mainline Receipt: `receipts/live-applies/2026-04-03-adr-0327-sectional-agent-discovery-mainline-live-apply.json`
- Implemented On: 2026-04-03
- Live Applied On: 2026-04-03
- Live Applied In Platform Version: N/A (repo-only control-plane change)
- Latest Verified Base: `origin/main@9badfab73` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0327-live-apply`
- Worktree: `.worktrees/ws-0327-live-apply`
- Owner: codex
- Depends On: `ADR 0163`, `ADR 0166`, `ADR 0168`, `ADR 0327`, `ADR 0335`, `ADR 0336`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `workstreams/active/ws-0327-live-apply.yaml`, `docs/workstreams/ws-0327-live-apply.md`, `docs/adr/0327-sectional-agent-discovery-registries-and-generated-onboarding-packs.md`, `docs/adr/.index.yaml`, `docs/runbooks/discovery-registry-maintenance.md`, `.gitignore`, `.repo-structure.yaml`, `.config-locations.yaml`, `docs/diagrams/agent-coordination-map.excalidraw`, `README.md`, `changelog.md`, `versions/stack.yaml`, `docs/discovery/`, `build/onboarding/`, `scripts/generate_discovery_artifacts.py`, `scripts/label_studio_sync.py`, `scripts/validate_public_entrypoints.py`, `scripts/validate_repo.sh`, `tests/test_generate_discovery_artifacts.py`, `tests/test_label_studio_sync.py`, `tests/test_validate_public_entrypoints.py`, `tests/test_validate_repo_cache.py`, `receipts/live-applies/2026-04-03-adr-0327-sectional-agent-discovery-live-apply.json`, `receipts/live-applies/2026-04-03-adr-0327-sectional-agent-discovery-mainline-live-apply.json`, `receipts/live-applies/evidence/2026-04-03-ws-0327-*`

## Scope

- split the monolithic discovery entrypoints into canonical concern-based source registries under `docs/discovery/`
- generate concise root `.repo-structure.yaml` and `.config-locations.yaml` entrypoints plus tracked onboarding packs under `build/onboarding/`
- validate the generated discovery artifacts and public-safe onboarding surfaces in repo automation
- carry the rebased exact-main proof onto `main` without bumping `VERSION` while the global release manager remains blocked by unrelated waiver receipts

## Verification

- The workstream was rebased from its original `origin/main@539204fd5c9e011bea51f0c096400ac6ad034926` baseline onto `origin/main@9badfab73`, resolving the generated-file conflicts by adopting the newer mainline shard-backed workstream contract, moving `ws-0327` into `workstreams/archive/2026/`, and regenerating `workstreams.yaml`, the ADR index, the discovery entrypoints, and the coordination diagram from source instead of hand-merging generated files.
- `git diff --check`, `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`, and `uv run --with pytest --with pyyaml python3 -m pytest -q tests/test_generate_discovery_artifacts.py tests/test_validate_public_entrypoints.py tests/test_validate_repo_cache.py tests/test_label_studio_sync.py` all passed on the rebased tree; the focused test slice returned `31 passed in 1.65s`.
- `./scripts/validate_repo.sh agent-standards generated-docs` passed after quoting the shard ADR id so the new `workstreams/` source preserved `0327` instead of YAML-octal `215`.
- `make validate` still fails on the current local tree because the latest-main shard-backed `workstreams/` files inherited from `origin/main` trip the controller-local `yamllint` indentation profile; that failure is preserved truthfully in `receipts/live-applies/evidence/2026-04-03-ws-0327-mainline-validate-r1.txt` and is not specific to the ADR 0327 discovery changes.
- `make remote-validate` passed on the recovered build-server path with `workstream-surfaces`, `agent-standards`, `ansible-syntax`, `schema-validation`, `atlas-lint`, `policy-validation`, `iac-policy-scan`, `alert-rule-validation`, `type-check`, and `dependency-graph` all green.
- `make pre-push-gate` then passed on the exact-main tree with the full promotion-facing gate surface green, including `documentation-index`, `yaml-lint`, `generated-docs`, `generated-portals`, `ansible-syntax`, `ansible-lint`, `semgrep-sast`, `security-scan`, and `integration-tests`.
- `git diff --check`, `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`, and `./scripts/validate_repo.sh agent-standards workstream-surfaces generated-docs` all passed on the final receipt-bearing tree before the last exact-main `make pre-push-gate` replay.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py status --json` still reports repository version `0.178.3`, platform version `0.130.98`, and a blocked release cut because three unrelated `controller_dependency_gap` waiver receipts remain open through `2026-04-06`; ADR 0327 therefore merges as exact-main truth but remains unreleased.

## Outcome

- ADR 0327 is implemented on the rebased exact-main tree, with authored discovery truth now split across `docs/discovery/repo-structure/`, `docs/discovery/config-locations/`, and `docs/discovery/onboarding-packs.yaml`.
- The top-level onboarding entrypoints remain available for AGENTS-driven quick starts, but they are now compact generated summaries instead of the only canonical source.
- Generated onboarding packs are now tracked intentionally under `build/onboarding/`, with `.gitignore` updated so the repo keeps those artifacts instead of silently dropping them.
- Repo automation now fails closed when the discovery artifacts drift or when public entrypoint scans would miss the new discovery/onboarding surfaces, and `scripts/label_studio_sync.py` no longer violates the retry guard because its version wait loop now uses the shared platform retry helper.

## Exact-Main Integration Status

- The exact-main integration is now carried by repository release `0.178.4`, including the updated branch-local and mainline receipts plus refreshed `workstreams.yaml` compatibility output.
- Repository release `0.178.4` records ADR 0327 in `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, and the generated release-note surfaces.
- ADR 0327 remains a repo-only control-plane change, so the platform version context stays `0.130.98`.
