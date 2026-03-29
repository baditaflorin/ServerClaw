# Workstream ws-0231-main-merge

- ADR: [ADR 0231](../adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md)
- Title: Integrate ADR 0231 local secret delivery into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.44
- Platform Version Observed During Merge: 0.130.40
- Release Date: 2026-03-28
- Branch: `codex/ws-0231-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0231-main-merge`
- Owner: codex
- Depends On: `ws-0231-live-apply`

## Purpose

Carry the verified ADR 0231 live-apply branch onto the latest `origin/main`,
cut the follow-on `0.177.44` repository release, refresh the protected
canonical-truth surfaces for the new control-plane recovery receipt, and rerun
the repository automation plus validation bundle from a clean integration
worktree before pushing `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0231-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.44.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0231-local-secret-delivery-via-openbao-agent-and-systemd-credentials.md`
- `docs/runbooks/configure-control-plane-recovery.md`
- `docs/workstreams/ws-0231-live-apply.md`
- `collections/ansible_collections/lv3/platform/roles/common/README.md`
- `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/common/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.hcl.j2`
- `collections/ansible_collections/lv3/platform/roles/common/templates/openbao-agent-systemd-credentials.service.j2`
- `collections/ansible_collections/lv3/platform/roles/control_plane_recovery/`
- `platform/ansible/plane.py`
- `tests/test_compose_runtime_secret_injection.py`
- `receipts/live-applies/2026-03-28-adr-0231-local-secret-delivery-live-apply.json`

## Plan

- register the integration branch so `workstream-surfaces` can validate the
  combined live-apply and protected release diff against `origin/main`
- cut release `0.177.44` without a platform-version bump because the live ADR
  0231 replay was already verified before the current `0.130.40` platform
  baseline
- refresh ADR 0231 canonical truth, control-plane recovery observed-state
  fields, and generated status artifacts before validating and pushing `main`

## Verification

- the branch first replayed the ADR 0231 release cut on older `origin/main` snapshots, then refreshed once onto the ADR 0207 `0.177.42` / `0.130.39` mainline, and finally refreshed again onto the ADR 0225 `0.177.43` / `0.130.40` mainline before the final recut
- `git merge --no-edit origin/main` raised one real content conflict in [`platform/ansible/plane.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0231-main-merge/platform/ansible/plane.py); the final merge kept the richer ADR 0231 HTTP or timeout retry diagnostics and restored the `time` import required by the newer Plane client tests on `main`
- the second refresh merged the ADR 0225 mainline cleanly, and the stash replay only conflicted in the protected release surfaces (`README.md`, `RELEASE.md`, `build/platform-manifest.json`, `docs/diagrams/agent-coordination-map.excalidraw`, and `versions/stack.yaml`) because `origin/main` already owned repository version `0.177.43`
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the merged ADR 0231 host-native OpenBao Agent plus systemd-credentials replay already verified on platform 0.130.38 while the current main baseline remains 0.130.40" --dry-run` reported `Current version: 0.177.43`, `Next version: 0.177.44`, and one unreleased note after the workstream was temporarily marked `merged` because the release manager ignores branch-owner `ready` workstreams
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "no live platform version bump; this release records the merged ADR 0231 host-native OpenBao Agent plus systemd-credentials replay already verified on platform 0.130.38 while the current main baseline remains 0.130.40"` prepared release `0.177.44`
- `uv run --with pyyaml python scripts/generate_adr_index.py --write`, `uvx --from pyyaml python scripts/generate_status_docs.py --write`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --write`, and `python3 scripts/generate_diagrams.py --write` refreshed the ADR index, README status fragments, platform manifest, and agent-coordination diagram on the final recut baseline
- `uv run --with pytest pytest -q tests/test_compose_runtime_secret_injection.py tests/test_plane_client.py` passed with `23 passed in 0.17s`
- `./scripts/validate_repo.sh workstream-surfaces agent-standards compose-runtime-envs retry-guard generated-docs generated-portals` passed on the `ready` validation state; the bundle still printed the existing non-blocking `.repo-structure.yaml` warning from ADR 0163 enforcement
- `uv run --with pyyaml --with jsonschema python scripts/live_apply_receipts.py --validate`, `uv run --with pyyaml python scripts/canonical_truth.py --check`, `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`, `uvx --from pyyaml python scripts/generate_status_docs.py --check`, and `git diff --check` all passed on the refreshed base
- the final `make validate` run completed successfully end to end on the `0.177.44` candidate; the bundle still prints the same seven warning-level `ansible-lint` findings in `control_plane_recovery/defaults/main.yml`, `monitoring_vm/tasks/main.yml`, `openbao_runtime/defaults/main.yml`, and `windmill_runtime/{defaults,tasks}/main.yml`, plus the same non-blocking `.repo-structure.yaml` warning, but the overall exit code is `0`

## Outcome

- Release `0.177.44` integrates ADR 0231 into `main` without a platform-version bump; the repository-version fields advanced while the current `platform_version` remained `0.130.40`, even though ADR 0231 itself first became true on platform version `0.130.38`
- `versions/stack.yaml` now points `control_plane_recovery` at receipt `2026-03-28-adr-0231-local-secret-delivery-live-apply` and records the verified `20260328T164431Z` runtime backup plus the `2026-03-28T16:45:06Z` restore drill on the current ADR 0225-updated mainline baseline
- the branch-local receipt remains the canonical live-apply evidence because the host-native secret delivery replay was already verified before the merged-main release cut; after this branch is fast-forwarded into `main`, no additional shared-truth edits remain beyond the push itself
