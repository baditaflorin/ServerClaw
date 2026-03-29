# Workstream ws-0274-live-apply: Live Apply ADR 0274 From Latest `origin/main`

- ADR: [ADR 0274](../adr/0274-governed-base-image-mirrors-and-warm-caches-for-repo-deployments.md)
- Title: Make the governed repo-deploy base-image warm-cache contract fully true on `coolify-lv3`
- Status: ready_to_merge (live applied)
- Implemented In Repo Version: pending latest-main integration
- Live Applied In Platform Version: 0.130.59
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0274-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0274-live-apply`
- Owner: codex
- Depends On: `adr-0194-coolify-paas-deploy-from-repo`, `adr-0224-self-service-repo-intake-and-agent-assisted-deployments`, `adr-0295-shared-artifact-cache-plane-for-container-and-package-dependencies`
- Conflicts With: none

## Scope

- add the approved repo-deploy base-image profile catalog required by ADR 0274
- converge a guest-local warm-plan, receipt, and refresh timer on `coolify-lv3`
- replay the latest `origin/main` Coolify service path and verify the deployment-lane cache surface end to end

## Non-Goals

- replacing ADR 0295 or ADR 0296 with a second build-host artifact-cache lane
- introducing a new public edge surface for cache listeners
- changing the top-level integrated release files until the exact-main work is ready for mainline integration

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

- `coolify-lv3` keeps the approved warm plan under `/opt/repo-deploy-image-cache/seed-plan.json`
- `coolify-lv3` keeps the latest warm receipt under `/opt/repo-deploy-image-cache/warm-status.json`
- `lv3-repo-deploy-image-cache.timer` remains active on `coolify-lv3`
- the governed repo-deploy base-image set is prewarmed before future production repo deploys rely on it

## Verification

- `python3 scripts/repo_deploy_image_cache.py validate` passed on the controller-local catalog.
- `python3 scripts/repo_deploy_image_cache.py plan` rendered the approved warm set from the committed catalog.
- `uv run --with pytest python -m pytest -q tests/test_repo_deploy_image_cache.py tests/test_coolify_playbook.py` returned `6 passed in 0.54s`.
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0274syntax1 --playbook playbooks/coolify.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check` passed.
- `uv run --with pyyaml --with jsonschema python scripts/workstream_surface_ownership.py --validate-registry --validate-branch` passed after the workstream registry entry and ownership manifest were aligned with the current mainline state.
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` passed with the new base-image profile catalog model and schema.
- `./scripts/validate_repo.sh data-models workstream-surfaces agent-standards` passed on the workstream branch after the generated validation artifacts were registered under a shared contract.
- `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:coolify`, `uv run --with pyyaml python scripts/standby_capacity.py --service coolify`, `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service coolify`, and `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service coolify --allow-in-place-mutation` all passed before the live replay.
- `make converge-coolify env=production` completed successfully with final recap `coolify-lv3 : ok=133 changed=16 unreachable=0 failed=0 skipped=12 rescued=0 ignored=0`, `nginx-lv3 : ok=70 changed=4 unreachable=0 failed=0 skipped=15 rescued=0 ignored=0`, and `proxmox_florin : ok=255 changed=5 unreachable=0 failed=0 skipped=125 rescued=0 ignored=0`.
- Direct SSH verification on `coolify-lv3` confirmed `lv3-repo-deploy-image-cache.timer` is `active` and `enabled`, the guest-local warm plan contains `5` approved seed refs, `/opt/repo-deploy-image-cache/warm-status.json` reports `result: pass` with `failed_pulls: 0`, and `docker image inspect` resolved all five warmed refs to local image IDs.
- Public verification confirmed `https://coolify.lv3.org/` and `https://coolify.lv3.org/login` both returned the expected TLS-backed Coolify login page, while `https://docs.lv3.org/robots.txt` and `https://changelog.lv3.org/robots.txt` still returned the expected `Disallow: /` policy text after the broader exact service replay.

## Results

- Before this workstream, `coolify-lv3` only had the first ADR 0274 slice: Docker used `https://mirror.gcr.io` and explicit public resolvers, but there was no governed repo-deploy warm plan, no warm receipt, and no refresh timer on the deployment lane.
- The branch now adds the approved deployment profile catalog, the `repo_deploy_image_cache` role, the guest-local warm-plan and receipt contract, and the scheduled timer-driven refresh surface required to make ADR 0274 operationally true on `coolify-lv3`.
- The live platform now holds the approved refs `docker.io/library/postgres:17.4-alpine3.21`, `mirror.gcr.io/library/alpine:3.21.3`, `mirror.gcr.io/library/golang:1.25.0-alpine3.21`, `mirror.gcr.io/library/node:22.14.0-bookworm-slim`, and `mirror.gcr.io/nginxinc/nginx-unprivileged:1.27.5-alpine3.21` under the governed warm-cache contract.

## Merge-To-Main Remaining

- cut the synchronized release from the latest `origin/main` baseline and update the protected integration files `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, and `build/platform-manifest.json`
- rerun the exact-main Coolify live-apply wrapper from that synchronized release commit so the final receipt cites a committed source tree instead of the branch-head worktree state
- record the canonical mainline receipt `receipts/live-applies/2026-03-30-adr-0274-governed-base-image-mirrors-and-warm-caches-mainline-live-apply.json`
- update the ADR 0274 metadata to the final integrated repo version once the synchronized mainline replay is complete
- rerun the full `generated-docs` and `generated-portals` validation steps from the synchronized main integration branch, because the workstream branch correctly stops at stale canonical truth instead of rewriting the protected `README.md` summary
