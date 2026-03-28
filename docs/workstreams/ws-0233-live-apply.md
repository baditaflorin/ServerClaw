# Workstream WS-0233: Signed Release Bundles Live Apply

- ADR: [ADR 0233](../adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md)
- Title: Live apply signed control-plane release bundles via Gitea Releases and Cosign
- Status: live_applied
- Implemented In Repo Version: 0.177.52
- Live Applied In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0233-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0233-live-apply`
- Owner: codex
- Depends On: `adr-0143-gitea-for-self-hosted-git-and-ci`, `adr-0168-automated-validation-gate`, `adr-0229-gitea-actions-runners-for-on-platform-validation-and-release-preparation`
- Conflicts With: none
- Shared Surfaces: `scripts/release_bundle.py`, `.gitea/workflows/release-bundle.yml`, `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`, `docs/runbooks/signed-release-bundles.md`, `docs/adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md`, `tests/test_release_bundle.py`, `workstreams.yaml`

## Scope

- implement repo-managed bundle assembly, signing, publication, and verification helpers for ADR 0233
- seed the required Cosign signing material into the private Gitea repository Actions secrets through the managed Gitea bootstrap path
- verify the full server-resident release-preparation path on the live Gitea runner from an isolated branch ref without rewriting shared release-track files on this branch
- record enough workstream-local evidence for a safe merge-to-main follow-up if the final canonical Gitea `main` sync still needs a dedicated integration step

## Expected Repo Surfaces

- `scripts/release_bundle.py`
- `.gitea/workflows/release-bundle.yml`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/templates/bootstrap-gitea.sh.j2`
- `tests/test_release_bundle.py`
- `tests/test_gitea_runtime_role.py`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/signed-release-bundles.md`
- `docs/adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md`
- `keys/gitea-release-bundle-cosign.pub`
- `docs/workstreams/ws-0233-live-apply.md`
- `workstreams.yaml`

## Expected Live Surfaces

- the private `ops/proxmox_florin_server` Gitea repo carries repo-managed Actions secrets for Cosign signing
- the self-hosted `docker-build-lv3` runner can assemble a control-plane bundle, sign it with Cosign, and publish the resulting assets into a Gitea Release
- a follow-up verification path can fetch the private release assets and confirm the published Sigstore bundle using the committed public key

## Verification

- `python3 -m py_compile scripts/release_bundle.py tests/test_release_bundle.py tests/test_gitea_runtime_role.py`
- `uv run --with pytest --with pyyaml pytest -q tests/test_release_bundle.py tests/test_gitea_runtime_role.py` returned `19 passed in 0.28s`
- `make syntax-check-gitea` and `./scripts/validate_repo.sh agent-standards`
- `make converge-gitea`
- authenticated Gitea API verification that repo secret `RELEASE_BUNDLE_REPO_TOKEN` exists beside the Cosign signing secrets
- branch push to the private Gitea remote that completed `release-bundle` workflow run `68` (`publish` job `85`, `verify` job `86`) and `validate` workflow run `69`
- controller-side `python3 scripts/release_bundle.py verify-release ... --release-tag bundle-branch-codex-ws-0233-main-merge-2fb56c14b62a ...` using the committed public key and a local Cosign binary

## Live Apply Outcome

- `make converge-gitea` completed successfully from the isolated latest-`origin/main` integration worktree with final recap `docker-build-lv3 ok=100 changed=5 failed=0`, `docker-runtime-lv3 ok=227 changed=2 failed=0`, `postgres-lv3 ok=24 changed=0 failed=0`, and `proxmox_florin ok=36 changed=4 failed=0`
- the managed Gitea bootstrap path now seeds repository secret `RELEASE_BUNDLE_REPO_TOKEN` from the mirrored admin token so private release assets can be replayed by both publish and verify workflows
- a private push of branch head `2fb56c14b62a73d0de47cb367a78c987dfd257c5` passed the full server-side gate and produced successful Gitea workflow runs `68` and `69` on the self-hosted runner path
- prerelease tag `bundle-branch-codex-ws-0233-main-merge-2fb56c14b62a` now carries the bundle tarball, checksum, and Sigstore bundle assets in private Gitea Releases
- direct controller-side replay of `verify-release` against that private release succeeded and reported bundle SHA-256 `da9139777eadf4d0a6f4b520decc40781fb13282486ef67326217990e6223a8f`

## Mainline Integration Outcome

- merged to `main` in repository version `0.177.52`
- bumped the live platform version to `0.130.43` after recording the merged-main-equivalent release-bundle receipt and carrying the verified signed-bundle evidence into canonical `main`
- updated `VERSION`, `changelog.md`, `RELEASE.md`, `docs/release-notes/0.177.52.md`, `README.md`, `versions/stack.yaml`, `build/platform-manifest.json`, and the ADR metadata only during the final mainline integration step

## Live Evidence

- branch-local live-apply receipt: `receipts/live-applies/2026-03-28-adr-0233-signed-release-bundles-live-apply.json`
- merged-main-equivalent live-apply receipt: `receipts/live-applies/2026-03-28-adr-0233-signed-release-bundles-mainline-live-apply.json`
- published prerelease tag: `bundle-branch-codex-ws-0233-main-merge-2fb56c14b62a`
- private release URL: `http://git.lv3.org:3009/ops/proxmox_florin_server/releases/tag/bundle-branch-codex-ws-0233-main-merge-2fb56c14b62a`

## Mainline Integration

- this workstream intentionally left `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, and the top-level README status summary untouched until the final mainline integration step that is now complete

## Merge-To-Main Notes

- remaining for merge to `main`: none
