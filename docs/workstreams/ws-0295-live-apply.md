# Workstream ws-0295-live-apply: Live Apply ADR 0295 From Latest `origin/main`

- ADR: [ADR 0295](../adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md)
- Title: Replay the merged artifact-cache runtime on `docker-build-lv3` and record the first platform version where it is true
- Status: live_applied
- Implemented In Repo Version: 0.177.73
- Live Applied In Platform Version: 0.130.59
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Latest Replay On: 2026-03-30
- Branch: `codex/ws-0295-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0295-live-apply-r2`
- Owner: codex
- Depends On: `ws-0274-artifact-cache-plane`, `adr-0089-build-cache`, `adr-0153-distributed-resource-lock-registry`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0295`, `docs/workstreams/ws-0295-live-apply.md`, `docs/runbooks/artifact-cache-runtime.md`, `docs/runbooks/configure-build-artifact-cache.md`, `docs/adr/.index.yaml`, `receipts/live-applies/`

## Scope

- replay `playbooks/services/build-artifact-cache.yml` from the current `origin/main` checkout
- verify the phase-1 artifact-cache listeners, seed plan, and BuildKit mirror wiring on `docker-build-lv3`
- record the mainline live-apply receipt and update the first platform version where ADR 0295 is true

## Non-Goals

- implementing ADR 0296 or provisioning a dedicated `artifact-cache-lv3` VM
- changing the merged repository implementation beyond narrow live-apply follow-through
- pretending the in-place mutation on `docker-build-lv3` is the preferred steady-state delivery path

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0295-live-apply.md`
- `docs/adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md`
- `docs/adr/.index.yaml`
- `receipts/live-applies/2026-03-30-adr-0295-shared-artifact-cache-plane-mainline-replay-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0295-shared-artifact-cache-plane-mainline-replay-live-apply.txt`

## Expected Live Surfaces

- `docker-build-lv3` listens on `10.10.10.30:5001-5004` for the repo-managed pull-through mirrors
- `/opt/artifact-cache/seed-plan.json` exists on `docker-build-lv3`
- `artifact-cache-docker-hub`, `artifact-cache-ghcr`, `artifact-cache-plane`, and `artifact-cache-n8n` are running on `docker-build-lv3`
- `docker buildx inspect lv3-cache --bootstrap` succeeds with the mirrored registry config still active

## Ownership Notes

- this workstream only claims the canonical live-apply replay from current `main`; the architecture and repo implementation stay with `ws-0274-artifact-cache-plane`
- `docker-build-lv3` is governed by ADR 0191 immutable guest replacement, so any in-place apply must remain a documented narrow exception in both the workstream notes and the receipt
- the resource lock for this replay should be taken on `vm:130` before mutation starts

## Verification

- `./scripts/validate_repo.sh workstream-surfaces data-models` passed from the fresh replay branch after `workstreams.yaml` was registered for `codex/ws-0295-live-apply-r2`.
- `./scripts/validate_repo.sh generated-docs` intentionally surfaced stale canonical truth while the replay workstream was marked `in_progress`; `uvx --from pyyaml python scripts/canonical_truth.py --write` refreshed `README.md`, and the governed `live-apply-service` wrapper then passed `check-canonical-truth`.
- `./scripts/validate_repo.sh agent-standards` passed with the existing non-blocking ADR index warning because adding `Implemented On` to ADR 0295 did not change the generated `.index.yaml` content.
- `uv run --with pytest python -m pytest -q tests/test_artifact_cache_seed.py tests/test_artifact_cache_runtime_role.py tests/test_docker_runtime_role.py tests/test_service_id_resolver.py` returned `18 passed in 1.10s`.
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0295syntax-r2 --playbook playbooks/services/build-artifact-cache.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check` passed.
- Pre-apply SSH verification on `docker-build-lv3` confirmed all four mirror endpoints responded, the four `artifact-cache-*` containers were already running, `lv3-buildkitd` was `active`, `docker buildx inspect lv3-cache --bootstrap` succeeded, and `apt-cacher-ng` served its report page, but `/opt/artifact-cache/seed-plan.json` still contained the earlier `41`-image warm set.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'` succeeded from latest `origin/main` base commit `aaab0fef79957f2c8b045b791fb117244d8873ec` with final recap `docker-build-lv3 : ok=122 changed=10 unreachable=0 failed=0 skipped=8 rescued=0 ignored=0`.
- Post-apply SSH verification confirmed all four mirror endpoints still responded, the four `artifact-cache-*` containers stayed up, the guest seed plan now contained `50` warmable images, `lv3-buildkitd` remained `active`, `docker buildx inspect lv3-cache --bootstrap` still succeeded, `apt-cacher-ng` still served its local report page, and the live nftables forward chain now contained accepts for both `172.16.0.0/12` and `192.168.0.0/16`.
- `python3 scripts/artifact_cache_seed.py --catalog config/image-catalog.json --catalog config/check-runner-manifest.json --catalog config/validation-gate.json --mirror docker.io=10.10.10.30:5001 --mirror ghcr.io=10.10.10.30:5002 --mirror artifacts.plane.so=10.10.10.30:5003 --mirror docker.n8n.io=10.10.10.30:5004 | jq '.seed_images | length'` also returned `50`, matching the refreshed guest-side seed plan.

## Results

- `origin/main` already contained the ADR 0295 implementation surfaces from `ws-0274-artifact-cache-plane`; this replay branch existed to re-run the merged automation from the latest mainline snapshot without reusing the older March 29 worktree.
- Before the March 30 replay, the live cache plane itself was healthy on `docker-build-lv3`: ports `5001-5004` responded, the four `artifact-cache-*` containers were up, `lv3-buildkitd` was active, and `apt-cacher-ng` was healthy. The drift was narrower but still real: `/opt/artifact-cache/seed-plan.json` had not been refreshed since the older `41`-image warm set.
- The March 30 exact-main replay from base commit `aaab0fef79957f2c8b045b791fb117244d8873ec` refreshed the guest seed plan to the current repo-derived `50`-image set and warmed the newly added mirrorable images through the existing cache plane.
- The shared wrapper also reasserted broader Docker-runtime compatibility on `docker-build-lv3`, including the live nftables forward accepts for `172.16.0.0/12` and `192.168.0.0/16`, a Docker restart when bridge chains were missing, updated public-edge hostname pinning, and a refreshed BuildKit socket permission.
- Protected release-truth files still do not need branch-local changes for this replay: ADR 0295 was already represented in canonical repo and platform history, so merge-to-main only needs the refreshed receipt/evidence, normalized ADR metadata, workstream notes, and the runbook clarification below.
