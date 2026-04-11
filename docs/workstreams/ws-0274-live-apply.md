# Workstream ws-0274-live-apply: Live Apply ADR 0274 From Latest `origin/main`

- ADR: [ADR 0274](../adr/0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments.md)
- Title: Make the governed repo-deploy base-image warm-cache contract fully true on `coolify`
- Status: live_applied
- Implemented In Repo Version: 0.177.104
- Live Applied In Platform Version: 0.130.69
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0274-main-merge-r4`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0274-mainline-v3`
- Owner: codex
- Depends On: `adr-0194-coolify-paas-deploy-from-repo`, `adr-0224-self-service-repo-intake-and-agent-assisted-deployments`, `adr-0295-shared-artifact-cache-plane-for-container-and-package-dependencies`
- Conflicts With: none

## Scope

- add the approved repo-deploy base-image profile catalog required by ADR 0274
- converge a guest-local warm-plan, receipt, and refresh timer on `coolify`
- replay the latest `origin/main` Coolify service path and verify the deployment-lane cache surface end to end

## Non-Goals

- replacing ADR 0295 or ADR 0296 with a second build-host artifact-cache lane
- introducing a new public edge surface for cache listeners
- broadening this workstream into unrelated Coolify or edge-policy changes beyond the exact-main replay fixes it exposed

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0274-live-apply.md`
- `docs/adr/0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments.md`
- `docs/runbooks/configure-coolify.md`
- `docs/runbooks/repo-deploy-base-image-cache.md`
- `config/repo-deploy-base-image-profiles.json`
- `docs/schema/repo-deploy-base-image-profiles.schema.json`
- `scripts/repo_deploy_image_cache.py`
- `collections/ansible_collections/lv3/platform/roles/repo_deploy_image_cache/`
- `playbooks/coolify.yml`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/`

## Expected Live Surfaces

- `coolify` keeps the approved warm plan under `/opt/repo-deploy-image-cache/seed-plan.json`
- `coolify` keeps the latest warm receipt under `/opt/repo-deploy-image-cache/warm-status.json`
- `lv3-repo-deploy-image-cache.timer` remains active on `coolify`
- the governed repo-deploy base-image set is prewarmed before future production repo deploys rely on it

## Verification

- `python3 scripts/repo_deploy_image_cache.py validate` passed on the controller-local catalog.
- `python3 scripts/repo_deploy_image_cache.py plan` rendered the approved warm set from the committed catalog.
- `uv run --with pytest pytest tests/test_repo_deploy_image_cache.py tests/test_coolify_playbook.py tests/test_coolify_runtime_role.py tests/test_docker_publication_assurance.py tests/test_tika_playbook.py tests/test_tika_runtime_role.py tests/test_docker_runtime_role.py tests/test_generate_platform_vars.py` returned `70 passed in 26.52s`.
- `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:coolify`, `uv run --with pyyaml python scripts/standby_capacity.py --service coolify`, `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service coolify`, and `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service coolify --allow-in-place-mutation` all passed before the live replay.
- `make live-apply-service service=coolify env=production EXTRA_ARGS='-e bypass_promotion=true'` completed successfully from the refreshed latest-main candidate with final recap `coolify : ok=161 changed=10 unreachable=0 failed=0 skipped=14 rescued=0 ignored=0`, `nginx-edge : ok=81 changed=4 unreachable=0 failed=0 skipped=16 rescued=0 ignored=0`, and `proxmox-host : ok=273 changed=5 unreachable=0 failed=0 skipped=134 rescued=0 ignored=0`.
- Direct SSH verification on `coolify` confirmed `sudo /usr/local/bin/lv3-docker-publication-assurance ...` returned `"ok": true` with summary `"docker publication contract is satisfied"` after the helper was hardened to tolerate hosts that ship `nftables` without an `iptables` binary.
- Direct SSH verification on `coolify` confirmed `/opt/repo-deploy-image-cache/warm-status.json` reported `result: pass`, `successful_pulls: 5`, `failed_pulls: 0`, `changed_count: 0`, `plan_generated_at: 2026-03-30T13:40:31Z`, and `warmed_at: 2026-03-30T13:40:37Z`, while `lv3-repo-deploy-image-cache.timer` remained `enabled` and `active`.
- Direct SSH verification on `coolify` confirmed `docker image inspect` resolved all five approved warmed refs locally.
- Public verification confirmed `https://coolify.example.com/` and `https://coolify.example.com/login` both returned the expected `302` redirect to `/oauth2/sign_in` with `x-robots-tag: noindex, nofollow`.
- Public verification confirmed `https://docs.example.com/robots.txt` and `https://changelog.example.com/robots.txt` still returned `Disallow: /` after the exact-main replay.
- Direct host verification confirmed `host=proxmox-host`, `kernel=6.17.13-2-pve`, `pve=pve-manager/9.1.6/71482d1833ded40a (running kernel: 6.17.13-2-pve)`, and `vm170=running`.
- The branch keeps both the initial failed replay evidence and the intermediate helper-verification evidence so another operator can see the exact-main issues that were fixed during integration: the helper installation path had to stop assuming the live-apply worktree layout, and the publication verifier had to treat a missing `iptables` binary as non-fatal on an `nftables`-only guest.

## Results

- Before this workstream, `coolify` only had the first ADR 0274 slice: Docker used `https://mirror.gcr.io` and explicit public resolvers, but there was no governed repo-deploy warm plan, no warm receipt, and no refresh timer on the deployment lane.
- This mainline candidate adds the approved deployment profile catalog, the `repo_deploy_image_cache` role, the guest-local warm-plan and receipt contract, the scheduled timer-driven refresh surface, and the Coolify bootstrap/publication hardening required to keep the replay self-healing from a separate worktree and on guests that rely on `nftables`.
- The live platform now holds the approved refs `docker.io/library/postgres:17.4-alpine3.21`, `mirror.gcr.io/library/alpine:3.21.3`, `mirror.gcr.io/library/golang:1.25.0-alpine3.21`, `mirror.gcr.io/library/node:22.14.0-bookworm-slim`, and `mirror.gcr.io/nginxinc/nginx-unprivileged:1.27.5-alpine3.21` under the governed warm-cache contract.
- While this branch was clearing the remote push gate, concurrent ADR 0296 work advanced `origin/main` to `0.177.103` on the same verified platform version `0.130.69`; ADR 0274 is therefore being recut on top as `0.177.104` without changing the already-verified live host baseline.

## Merge-To-Main Remaining

- none after the `0.177.104` post-ADR-0296 integration and canonical receipt refresh
