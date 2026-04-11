# Workstream ws-0246-main-merge

- ADR: [ADR 0246](../adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md)
- Title: Integrate ADR 0246 runtime-state semantics into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.60
- Platform Version Observed During Merge: 0.130.44
- Release Date: 2026-03-29
- Branch: `codex/ws-0246-main-merge-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0246-main-merge-v2`
- Owner: codex
- Depends On: `ws-0246-live-apply`

## Purpose

Carry the verified ADR 0246 live-apply branch onto the current `origin/main`,
re-cut the repository release as `0.177.60`, refresh the protected canonical
truth and generated status surfaces, and preserve the already-verified platform
baseline without a second literal-main replay.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0246-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.60.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0246-startup-readiness-liveness-and-degraded-state-semantics.md`
- `docs/workstreams/ws-0246-live-apply.md`
- `docs/runbooks/health-probe-contracts.md`
- `docs/runbooks/service-uptime-contracts.md`
- `docs/runbooks/scaffold-new-service.md`
- `config/health-probe-catalog.json`
- `playbooks/tasks/post-verify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `platform/health/semantics.py`
- `platform/health/composite.py`
- `platform/graph/client.py`
- `platform/world_state/workers.py`
- `scripts/platform_observation_tool.py`
- `scripts/scaffold_service.py`
- `scripts/validate_repository_data_models.py`
- `tests/test_post_verify_tasks.py`
- `tests/test_platform_observation_tool.py`
- `tests/test_world_state_workers.py`
- `tests/test_health_composite.py`
- `tests/test_scaffold_service.py`
- `tests/unit/test_graph_client.py`
- `receipts/live-applies/2026-03-28-adr-0246-runtime-state-semantics-live-apply.json`

## Plan

- replay the verified ADR 0246 branch commits onto the newer `origin/main`
  baseline after ADR 0253 advanced the current release and coordination diagram
  surfaces
- cut release `0.177.60` without a platform-version bump because the verified
  ADR 0246 live apply already ran on the current `0.130.44` mainline baseline
- refresh ADR metadata, canonical truth, the platform manifest, and generated
  diagram artifacts before validating and pushing `origin/main`

## Verification

- `git merge --no-ff codex/ws-0246-live-apply` replayed the rebased ADR 0246
  live-apply commits cleanly on top of `origin/main` commit
  `31a0e8da28e92c6c8280116d49ff96ce87871433`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0246 runtime-state rollout while the current mainline platform baseline remains 0.130.44" --dry-run`
  reported `Current version: 0.177.59`, `Next version: 0.177.60`, and
  `Unreleased notes: 1` after correcting ADR 0253's missing
  `included_in_repo_version` marker in `workstreams.yaml`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the verified ADR 0246 runtime-state rollout while the current mainline platform baseline remains 0.130.44"`
  prepared release `0.177.60`
- `uv run --with pyyaml python scripts/generate_diagrams.py --write` refreshed
  the coordination diagram after the `ws-0246-main-merge` workstream entry was
  added, and `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write`
  refreshed `build/platform-manifest.json` to repo version `0.177.60`

## Outcome

- release `0.177.60` carries the verified ADR 0246 runtime-state rollout onto
  `main` without a platform-version bump; the current mainline platform
  baseline remains `0.130.44`
- the canonical live-apply receipt remains
  `receipts/live-applies/2026-03-28-adr-0246-runtime-state-semantics-live-apply.json`
  because the rebased live replay and verification already ran before this
  follow-on release cut
