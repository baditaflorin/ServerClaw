# Workstream WS-0233: Signed Release Bundles Live Apply

- ADR: [ADR 0233](../adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md)
- Title: Live apply signed control-plane release bundles via Gitea Releases and Cosign
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
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
- a follow-up verification path can fetch the private release assets and confirm the detached Cosign signature using the committed public key

## Verification

- pending implementation

## Outcome

- pending implementation

## Mainline Integration

- this workstream intentionally leaves `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, and the top-level README status summary untouched until a final mainline integration step

## Notes For The Next Assistant

- the live Gitea repository `main` currently trails `origin/main`; branch-safe verification should prefer a dedicated workstream branch ref in Gitea unless this session also owns the final repo sync
