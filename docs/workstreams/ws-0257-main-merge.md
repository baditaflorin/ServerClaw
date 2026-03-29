# Workstream ws-0257-main-merge

- ADR: [ADR 0257](../adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md)
- Title: Integrate ADR 0257 exact-main replay onto `origin/main`
- Status: `in_progress`
- Branch: `codex/ws-0257-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0257-main-merge`
- Owner: codex
- Depends On: `ws-0257-live-apply`

## Purpose

Carry the verified ADR 0257 ServerClaw skill-pack contract onto the latest
`origin/main`, replay the Windmill and API gateway live applies from that exact
mainline source tree, and then refresh the protected canonical-truth surfaces
only after the integrated platform verification is complete.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0257-main-merge.md`
- `docs/workstreams/adr-0257-serverclaw-skill-packs-live-apply.md`
- `docs/adr/0257-openclaw-compatible-skill-md-packs-and-workspace-precedence-for-serverclaw.md`
- `docs/adr/.index.yaml`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `receipts/live-applies/`

## Verification

- fetched `origin/main` on 2026-03-30 and confirmed the current tip as
  `020c5f5ad` with repo version `0.177.88`
- replayed `make converge-windmill` from this worktree and reached
  `Result: PASS (converge-windmill)` with a clean `PLAY RECAP`; the replay
  exercised the Docker bridge-chain recovery path that this branch hardens
- revalidated the repo-side regressions that unblock the exact-main replay:
  `tests/test_api_gateway_runtime_role.py`,
  `tests/test_config_merge_windmill.py`,
  `tests/test_docker_runtime_role.py`,
  `tests/test_ephemeral_lifecycle_repo_surfaces.py`,
  `tests/test_validation_gate.py`,
  `tests/test_validation_gate_windmill.py`,
  `tests/test_windmill_operator_admin_app.py`
- direct post-rebase gateway, controller, and runtime-assurance checks still
  remain before the final merge-to-main step

## Outcome

- branch-local replay hardening is implemented, including:
  - governed ServerClaw skill-pack sync additions for the API gateway runtime
  - macOS-safe API gateway tree sync that avoids AppleDouble/xattr ownership
    leakage during remote extraction
  - repo-root path resolution for `scripts/gate_status.py`
  - retry classification for transient Windmill backend SQL transport failures
  - Docker/Windmill recovery for missing `DOCKER` and `DOCKER-FORWARD` chains
  - workspace-scoped Windmill schedule flag convergence using one SQL update
- protected integration files intentionally remain untouched here until the
  rebased branch finishes its final live verification on top of the latest
  `origin/main`
