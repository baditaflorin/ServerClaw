# Workstream ws-0242-main-merge

- ADR: [ADR 0242](../adr/0242-guided-human-onboarding-via-shepherd-tours.md)
- Title: Integrate ADR 0242 guided onboarding into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.58
- Platform Version Observed During Merge: 0.130.44
- Release Date: 2026-03-29
- Branch: `codex/ws-0242-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0242-main-integration`
- Owner: codex
- Depends On: `ws-0242-live-apply`

## Purpose

Carry the verified ADR 0242 live-apply branch onto the latest `origin/main`,
re-cut the repository release as `0.177.58` after ADR 0250 advanced `main` to
`0.177.57`, refresh the protected canonical-truth and generated status
surfaces, and push the fully validated result to `origin/main` without changing
the current platform baseline.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0242-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.58.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0242-guided-human-onboarding-via-shepherd-tours.md`
- `docs/workstreams/ws-0242-live-apply.md`
- `docs/runbooks/configure-windmill.md`
- `docs/runbooks/windmill-operator-access-admin.md`
- `docs/runbooks/operator-onboarding.md`
- `docs/runbooks/operator-offboarding.md`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `config/windmill/apps/f/lv3/operator_access_admin.raw_app/`
- `scripts/validate_repo.sh`
- `tests/test_windmill_operator_admin_app.py`
- `receipts/live-applies/2026-03-28-adr-0242-guided-human-onboarding-live-apply.json`

## Plan

- replay the verified ADR 0242 branch commits onto the newer `origin/main`
  baseline after ADR 0250 advanced the current release and platform metadata
- cut release `0.177.58` without a platform-version bump because the verified
  ADR 0242 live apply already ran before the current `0.130.44` mainline
  baseline
- refresh ADR metadata, canonical truth, the platform manifest, and generated
  status artifacts before validating and pushing `origin/main`

## Verification

- `git rebase origin/main` replayed the four ADR 0242 branch commits cleanly on
  top of `origin/main` commit `5d2df00b49dd24f05d41885d7ecd661ba34535ef` after
  skipping the stale `0.177.57` release-cut commits that would have overwritten
  newer ADR 0250 mainline truth
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0242 Shepherd-tour rollout while the current mainline platform baseline remains 0.130.44" --dry-run`
  reported `Current version: 0.177.57`, `Next version: 0.177.58`, and
  `Unreleased notes: 1`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0242 Shepherd-tour rollout while the current mainline platform baseline remains 0.130.44"`
  prepared release `0.177.58`

## Outcome

- release `0.177.58` carries the verified ADR 0242 Shepherd-tour rollout onto
  `main` without a platform-version bump; the current mainline platform
  baseline remains `0.130.44`, while ADR 0242 itself first became true on
  platform version `0.130.43`
- the canonical live-apply receipt remains
  `receipts/live-applies/2026-03-28-adr-0242-guided-human-onboarding-live-apply.json`
  because the latest-`origin/main` replay was already verified before this
  follow-on release cut
