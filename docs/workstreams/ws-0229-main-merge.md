# Workstream ws-0229-main-merge

- ADR: [ADR 0229](../adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md)
- Title: Integrate ADR 0229 live apply into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.45
- Platform Version Observed During Merge: 0.130.40
- Release Date: 2026-03-28
- Branch: `codex/ws-0229-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0229-main-merge`
- Owner: codex
- Depends On: `ws-0229-live-apply`
- Conflicts With: none

## Purpose

Carry the verified ADR 0229 live-apply evidence onto the latest `origin/main`,
cut the protected release files from that merged candidate, and keep the
already-live platform truth aligned with the documented runner verification.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0229-main-merge.md`
- `VERSION`
- `changelog.md`
- `RELEASE.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.45.md`
- `versions/stack.yaml`
- `README.md`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation.md`
- `docs/workstreams/ws-0229-live-apply.md`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/validate-repository-automation.md`
- `docs/adr/.index.yaml`
- `receipts/live-applies/2026-03-28-adr-0229-gitea-actions-runners-live-apply.json`

## Plan

- rebuild the integration branch from the latest `origin/main`
- merge the verified `codex/ws-0229-live-apply` branch into the dedicated main-merge worktree
- cut release `0.177.45` without a new platform-version bump because ADR 0229 was already live before the concurrent ADR 0231 mainline release
- refresh generated canonical-truth surfaces and re-run the repository validation gate before pushing `origin/main`

## Result

- Release `0.177.45` integrates ADR 0229 into `origin/main` by carrying forward the latest-main verification replay, the private Gitea push-gate proof, and workflow run `36` on runner `docker-build-lv3`.
- The repository version advances while platform version `0.130.40` stays unchanged because this merge records already-live runner truth rather than introducing a new post-merge live mutation.
- `versions/stack.yaml`, `README.md`, and release history now align with the refreshed ADR 0229 receipt and workstream metadata on top of the concurrent ADR 0225 mainline release.

## Verification

- `git merge --no-ff codex/ws-0229-live-apply` replayed the verified workstream changes onto the clean integration branch from latest `origin/main`.
- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --platform-impact "no additional platform version bump; this release records the already-live ADR 0229 Gitea Actions runner rollout on current platform version 0.130.40 after refreshing the latest-main convergence and server-side validation proof" --dry-run` confirmed the next release cut before writing files.
- `LV3_SKIP_OUTLINE_SYNC=1 python3 scripts/release_manager.py --bump patch --platform-impact "no additional platform version bump; this release records the already-live ADR 0229 Gitea Actions runner rollout on current platform version 0.130.40 after refreshing the latest-main convergence and server-side validation proof"` prepared release `0.177.45`.
- `python3 scripts/canonical_truth.py --write`, `python3 scripts/generate_diagrams.py --write`, and `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --write` refreshed the derived integration surfaces after the final release metadata landed.
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_gitea_runtime_role.py`, `./scripts/validate_repo.sh agent-standards`, `uv run --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py --validate`, `python3 scripts/canonical_truth.py --check`, `python3 scripts/generate_diagrams.py --check`, `uv run --with pyyaml --with jsonschema python3 scripts/platform_manifest.py --check`, and `git diff --check` all passed on the integrated `0.177.45` candidate.
- `make pre-push-gate` passed on the integrated branch, including `alert-rule-validation`, `ansible-lint`, `ansible-syntax`, `artifact-secret-scan`, `dependency-direction`, `dependency-graph`, `integration-tests`, `packer-validate`, `schema-validation`, `security-scan`, `service-completeness`, `tofu-validate`, `type-check`, and `yaml-lint`.
