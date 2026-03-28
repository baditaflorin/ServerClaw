# Workstream WS-0206 Main Merge

- ADR: [ADR 0206](../adr/0206-ports-and-adapters-for-external-integrations.md)
- Title: Integrate the verified ADR 0206 live apply into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.33
- Platform Version Observed During Merge: 0.130.36
- Release Date: 2026-03-28
- Branch: `codex/ws-0206-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0206-main-merge`
- Owner: codex
- Depends On: `ws-0206-live-apply`

## Scope

- merge the finished `codex/ws-0206-live-apply` branch on top of the latest `origin/main`
- cut the mainline `0.177.33` release for ADR 0206 without changing the live platform version
- refresh canonical truth, release notes, ADR metadata, and generated manifest surfaces on the merged tree
- rerun the operator-access verification slice from the release candidate worktree before pushing `main`

## Verification

- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the merged ADR 0206 operator-access ports/adapters replay and the verified OpenBao operator-entity repair already live on platform 0.130.35" --dry-run` reported `Current version: 0.177.32`, `Next version: 0.177.33`, and one unreleased note
- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the merged ADR 0206 operator-access ports/adapters replay and the verified OpenBao operator-entity repair already live on platform 0.130.35"` prepared release `0.177.33`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write` and `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write` refreshed the generated metadata surfaces
- after the first push attempt surfaced a stale generated diagram in the dependency-graph gate, `python3 scripts/generate_diagrams.py --write` refreshed `docs/diagrams/agent-coordination-map.excalidraw` and `uv run --with jsonschema python scripts/validate_dependency_graph.py`, `uv run --with jsonschema python scripts/generate_dependency_diagram.py --check`, and `python3 scripts/generate_diagrams.py --check` then passed locally
- `uv run --with pytest --with pyyaml pytest -q tests/test_controller_automation_toolkit.py tests/test_operator_manager.py tests/test_operator_access_adapters.py tests/test_release_manager.py` passed with `22 passed in 0.23s`
- `uv run --with requests --with pyyaml python scripts/operator_manager.py validate`, `uv run --with requests --with pyyaml python scripts/operator_manager.py --emit-json quarterly-review --dry-run`, `python3 scripts/operator_access_inventory.py --id florin-badita --format json --offline`, and the controller-secret-backed live `python3 scripts/operator_access_inventory.py --id florin-badita --format json` all passed from this merged-main worktree
- `uv run --with pyyaml python scripts/canonical_truth.py --check`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, `python3 scripts/release_manager.py status`, and `./scripts/validate_repo.sh agent-standards` all passed after the integration branch was registered in `workstreams.yaml`

## Outcome

- ADR 0206 is now attributed to repo version `0.177.33` on `main`
- `versions/stack.yaml` now points `operator_access` and the related ADR 0206 capability receipts to `2026-03-28-adr-0206-ports-and-adapters-live-apply`
- the merged tree preserves platform version `0.130.36` because the live repair already happened before the mainline release cut
