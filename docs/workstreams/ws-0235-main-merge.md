# Workstream ws-0235-main-merge

- ADR: [ADR 0235](../adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md)
- Title: Integrate ADR 0235 cross-application launcher into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.69
- Platform Version Observed During Merge: 0.130.47
- Release Date: 2026-03-29
- Branch: `codex/ws-0235-main-merge-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-main-merge-r3`
- Owner: codex
- Depends On: `ws-0235-live-apply`

## Purpose

Carry the verified ADR 0235 launcher rollout onto the latest `origin/main`, cut
release `0.177.69`, refresh the protected canonical-truth surfaces, and
re-verify the interactive ops portal from the exact mainline candidate.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0235-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.69.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0235-cross-application-launcher-and-favorites-via-patternfly-application-launcher.md`
- `docs/workstreams/ws-0235-live-apply.md`
- `docs/runbooks/platform-operations-portal.md`
- `scripts/ops_portal/app.py`
- `scripts/ops_portal/runtime_assurance.py`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/ops_portal_runtime/tasks/main.yml`
- `tests/test_interactive_ops_portal.py`
- `tests/test_ops_portal_runtime_role.py`
- `tests/test_runtime_assurance_scoreboard.py`
- `receipts/live-applies/2026-03-29-adr-0235-cross-application-launcher-live-apply.json`

## Verification

- `git fetch origin` confirmed this integration branch still contained the
  latest `origin/main` before the protected release cut
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.47 after the exact-main ADR 0235 replay re-verifies the PatternFly-style cross-application launcher and session-scoped favorites on ops.lv3.org while preserving the authenticated edge contract on top of the 0.130.46 baseline" --released-on 2026-03-29 --dry-run`
  reported `Current version: 0.177.68`, `Next version: 0.177.69`, and
  `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version advances to 0.130.47 after the exact-main ADR 0235 replay re-verifies the PatternFly-style cross-application launcher and session-scoped favorites on ops.lv3.org while preserving the authenticated edge contract on top of the 0.130.46 baseline" --released-on 2026-03-29`
  prepared release `0.177.69`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=ops_portal env=production EXTRA_ARGS='-e bypass_promotion=true -e ops_portal_repo_root=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0235-main-merge-r3'`
  completed successfully with final recap
  `docker-runtime-lv3 ok=129 changed=14 failed=0 skipped=14`

## Outcome

- release `0.177.69` carries ADR 0235 onto `main`
- the current live platform baseline after the exact-main replay is `0.130.47`
