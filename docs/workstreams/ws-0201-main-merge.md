# Workstream ws-0201-main-merge

- ADR: [ADR 0201](../adr/0201-harbor-container-registry-with-cve-scanning.md)
- Title: Finalize ADR 0201 Harbor exact-main evidence on `origin/main`
- Status: merged
- Included In Repo Version: 0.177.62
- Platform Version Observed During Merge: 0.130.45
- Release Date: 2026-03-29
- Branch: `main`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0246-main-push`
- Owner: codex
- Depends On: `ws-0201-live-apply`

## Purpose

Carry the verified ADR 0201 Harbor workstream onto the current `origin/main`,
preserve the rebased workstream live-apply receipt, add the final exact-main
Harbor recovery fix for OIDC bootstrap after published-port loss, and recut the
protected release-truth surfaces on top of repository version `0.177.61` with a
live platform bump to `0.130.45`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0201-live-apply.md`
- `docs/workstreams/ws-0201-main-merge.md`
- `docs/adr/0201-harbor-container-registry-with-cve-scanning.md`
- `docs/runbooks/configure-harbor.md`
- `collections/ansible_collections/lv3/platform/roles/harbor_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `tests/test_harbor_runtime_role.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_remote_exec.py`
- `tests/test_generate_platform_vars.py`
- `receipts/live-applies/2026-03-28-adr-0201-harbor-live-apply.json`
- `receipts/live-applies/2026-03-29-adr-0201-harbor-mainline-live-apply.json`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.62.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/adr/.index.yaml`

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_harbor_runtime_role.py` returned `5 passed` after the exact-main OIDC readiness recovery block was added for published-port loss on `127.0.0.1:8095`.
- `make converge-harbor` completed successfully from the exact-main merge worktree after the recovery fix, preserving the Harbor runtime and shared edge publication from the current `main` baseline.
- `curl -fsS --max-time 20 https://registry.lv3.org/api/v2.0/ping` returned `Pong` and `curl -skI --max-time 20 https://registry.lv3.org/v2/` returned `HTTP/2 401` with `docker-distribution-api-version: registry/2.0` and the expected bearer-auth challenge.
- On `docker-runtime-lv3`, `curl -fsS --max-time 20 http://127.0.0.1:8095/api/v2.0/ping` returned `Pong` and `curl -sSI --max-time 20 http://127.0.0.1:8095/v2/` returned `HTTP/1.1 401 Unauthorized`, proving Harbor's registry/auth path recovered locally from the earlier stalled port-publication state.
- On `docker-build-lv3`, `docker pull registry.lv3.org/check-runner/python:3.12.10` completed successfully and `docker image inspect` reported `registry.lv3.org/check-runner/python@sha256:9dd2ea22539ed61d0aed774d0f29d2a2de674531b80f852484849500d64169ff`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py --bump patch --platform-impact "platform version bumps to 0.130.45 after the merged-main Harbor replay re-verified registry.lv3.org, runtime-local Harbor auth, and docker-build check-runner pulls from Harbor with the exact-main OIDC readiness recovery in place" --released-on 2026-03-29 --dry-run` reported the `0.177.61` to `0.177.62` release plan before the release was cut.
- `make remote-validate` passed through the remote build path with `alert-rule-validation`, `ansible-syntax`, `dependency-graph`, `policy-validation`, `schema-validation`, and `type-check` all green from the merged `main` worktree.
- `make remote-pre-push` passed through the same remote build path with `ansible-lint`, `artifact-secret-scan`, `dependency-direction`, `integration-tests`, `packer-validate`, `security-scan`, `service-completeness`, `tofu-validate`, `yaml-lint`, and the rest of the governed pre-push suite all green from the merged `main` worktree.

## Outcome

- Release `0.177.62` records ADR 0201 on `main`, while the current integrated platform baseline advances from `0.130.44` to `0.130.45` because Harbor was re-applied and re-verified from exact mainline state.
- The canonical exact-main Harbor receipt is `receipts/live-applies/2026-03-29-adr-0201-harbor-mainline-live-apply.json`.
- ADR 0201 itself first became true on platform version `0.130.43`, and the integrated exact-main follow-up preserves that first-implementation fact while recording the new mainline platform baseline.
