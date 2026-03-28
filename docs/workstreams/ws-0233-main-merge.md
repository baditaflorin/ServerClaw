# Workstream ws-0233-main-merge

- ADR: [ADR 0233](../adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md)
- Title: Integrate ADR 0233 signed release bundles into `origin/main`
- Status: merged
- Included In Repo Version: 0.177.53
- Platform Version Observed During Merge: 0.130.42
- Release Date: 2026-03-28
- Branch: `codex/ws-0233-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0233-main-merge`
- Owner: codex
- Depends On: `ws-0233-live-apply`

## Purpose

Carry the verified ADR 0233 bundle-signing implementation onto the latest
`origin/main`, replay the live Gitea release-bundle path from the merged-main
candidate, refresh the protected canonical-truth surfaces for the follow-on
release cut, and push the integrated result to `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0233-main-merge.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.53.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/.index.yaml`
- `docs/adr/0233-signed-release-bundles-via-gitea-releases-and-cosign.md`
- `docs/runbooks/configure-gitea.md`
- `docs/runbooks/signed-release-bundles.md`
- `docs/workstreams/ws-0233-live-apply.md`
- `.config-locations.yaml`
- `.gitea/workflows/release-bundle.yml`
- `keys/gitea-release-bundle-cosign.pub`
- `scripts/release_bundle.py`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `tests/test_release_bundle.py`
- `tests/test_gitea_runtime_role.py`
- `receipts/live-applies/2026-03-28-adr-0233-signed-release-bundles-live-apply.json`
- `receipts/live-applies/2026-03-28-adr-0233-signed-release-bundles-mainline-live-apply.json`

## Plan

- merge the verified ADR 0233 runtime surfaces onto the latest `origin/main`
- refresh the protected release and canonical-truth files for release `0.177.53`
- carry both the isolated-worktree and merged-main-equivalent live-apply receipts into the final integration branch before pushing `main`

## Verification

- `git fetch origin` confirmed the integration branch stayed current with `origin/main` before the release recut
- `python3 -m py_compile scripts/release_bundle.py tests/test_release_bundle.py tests/test_gitea_runtime_role.py` passed
- `uv run --with pytest --with pyyaml pytest -q tests/test_release_bundle.py tests/test_gitea_runtime_role.py` returned `19 passed in 0.28s`
- `make syntax-check-gitea`, `./scripts/validate_repo.sh agent-standards`, `uv run --with jsonschema --with pyyaml python scripts/validate_dependency_graph.py`, `uv run --with jsonschema --with pyyaml python scripts/generate_dependency_diagram.py --check`, `uv run --with pyyaml python scripts/generate_diagrams.py --check`, and `git diff --check` all passed on the candidate before the final release metadata landed
- the rebased candidate replayed `make converge-gitea`, seeded `RELEASE_BUNDLE_REPO_TOKEN`, passed the private Gitea push gate, completed `release-bundle` workflow run `68` plus `validate` run `69`, and succeeded on direct controller-side `verify-release`
- the final integration cut release `0.177.53`, regenerated the ADR index, README status fragments, platform manifest, and diagrams, then re-ran the repository validation and automation checks before the push to `origin/main`

## Outcome

- release `0.177.53` integrates ADR 0233 into `main` by carrying forward the verified private Gitea release-bundle publication path, the durable repository-token secret seeding, and controller-side Cosign verification against private release assets
- the repository truth and live platform truth now align on signed release bundles as an implemented capability, with canonical receipt `2026-03-28-adr-0233-signed-release-bundles-mainline-live-apply` mapped under `signed_release_bundles`
- platform version `0.130.43` records the merged-main-equivalent verification replay even though the successful publication and verification proof ran from the dedicated integration worktree before the final fast-forward to `origin/main`
