# Workstream ws-0241-main-merge

- ADR: [ADR 0241](../adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md)
- Title: Integrate ADR 0241 rich content and inline knowledge editing into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.61
- Platform Version Observed During Merge: 0.130.44
- Release Date: 2026-03-29
- Branch: `codex/ws-0241-main-merge-r3`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0241-main-merge-r3`
- Owner: codex
- Depends On: `ws-0241-live-apply`

## Purpose

Carry the verified ADR 0241 live-apply branch onto the latest `origin/main`,
refresh the protected canonical-truth and release surfaces from the
`0.177.60` baseline, and publish the exact-main integration without changing
the live platform baseline.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0241-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.61.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`
- `docs/adr/0241-rich-content-and-inline-knowledge-editing-via-tiptap.md`
- `docs/workstreams/ws-0241-live-apply.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/runbooks/validation-gate.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`
- `config/windmill/apps/wmill-lock.yaml`
- `config/windmill/scripts/operator-update-notes.py`
- `scripts/operator_manager.py`
- `tests/test_operator_manager.py`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-29-adr-0241-rich-content-and-inline-knowledge-editing-live-apply.json`

## Verification

- replay the verified ADR 0241 branch commits onto the latest `origin/main`
  baseline after ADR 0246 advanced `main` to `0.177.60`
- `git cherry-pick 2327d53a`, `git cherry-pick 32a82841`, and
  `git cherry-pick 2c3cd133` replayed the verified ADR 0241 branch onto
  `origin/main` commit `e45da1e3b7c5a24b67cdd6b8eeac59fb150b97af`
- the operator-access admin app state on this branch keeps both ADR 0241 rich
  notes and ADR 0242 guided tours on the same shared Windmill surface
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0241 Tiptap rich-notes rollout while the current mainline platform baseline remains 0.130.44" --dry-run`
  reported `Current version: 0.177.60`, `Next version: 0.177.61`, and
  `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0241 Tiptap rich-notes rollout while the current mainline platform baseline remains 0.130.44"`
  prepared release `0.177.61`

## Outcome

- release `0.177.61` carries the verified ADR 0241 Tiptap rich-notes rollout
  onto `main` without a platform-version bump; the current mainline platform
  baseline remains `0.130.44`, while ADR 0241 itself first became true on
  platform version `0.130.43`
- the canonical live-apply receipt remains
  `receipts/live-applies/2026-03-29-adr-0241-rich-content-and-inline-knowledge-editing-live-apply.json`
  because the verified exact-main replay already completed before this release
  cut
- `versions/stack.yaml` now points both `operator_access` and `windmill` to the
  ADR 0241 receipt, reflecting the latest verified live evidence on those
  shared surfaces
