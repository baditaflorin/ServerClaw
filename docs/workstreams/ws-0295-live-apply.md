# Workstream ws-0295-live-apply: Live Apply ADR 0295 From Latest `origin/main`

- ADR: [ADR 0295](../adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md)
- Title: Replay the merged artifact-cache runtime on `docker-build-lv3` and record the first platform version where it is true
- Status: in_progress
- Implemented In Repo Version: 0.177.73
- Live Applied In Platform Version: 0.130.59
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
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

- `make ensure-resource-lock-registry`
- `python3 scripts/resource_lock_tool.py acquire --resource vm:130 --holder agent:codex/ws-0295-live-apply --lock-type exclusive --ttl-seconds 7200 --context-id ws-0295-live-apply`
- `uv run --with pytest python -m pytest -q tests/test_artifact_cache_runtime_role.py tests/test_service_id_resolver.py`
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0295syntax2 --playbook playbooks/services/build-artifact-cache.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'` completed successfully from synchronized commit `b80cc3a886539bb467a7ed54b2e606180cd08f44` with `docker-build-lv3 : ok=103 changed=9 unreachable=0 failed=0 skipped=7 rescued=0 ignored=0`
- `ssh ... ops@10.10.10.30 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.30:${port}/v2/" >/dev/null; done; docker buildx inspect lv3-cache --bootstrap >/dev/null; jq ".seed_images | length" /opt/artifact-cache/seed-plan.json'` confirmed all four mirror endpoints responded, the four `artifact-cache-*` containers were running, the exact-main seed plan contained `41` warmable images, `lv3-buildkitd` stayed `active`, and `apt-cacher-ng` still served its local report page

## Replay Notes

- This replay branch re-runs the already-merged ADR 0295 automation from the latest `origin/main` head so the current mainline validation, guardrail, and live-apply paths are exercised again without reusing the earlier March 29 worktree.
- The branch intentionally avoids protected release-truth files unless a fresh exact-main replay proves they actually need an update.

## Results

- `origin/main` already contains the ADR 0295 implementation surfaces from `ws-0274-artifact-cache-plane`; this workstream exists to make that merged truth live and to update the canonical platform state afterward.
- Before the replay, `docker-build-lv3` still had `apt-cacher-ng` and `lv3-buildkitd` active but no `artifact-cache-*` containers, no listeners on ports `5001-5004`, and no `/opt/artifact-cache/seed-plan.json`.
- The first branch-local replay exposed a real runtime defect in the original merged implementation: the registry mirrors crashed on Docker bridge DNS lookups to `127.0.0.11`, so this workstream corrected the artifact-cache containers to run on host networking and taught the generic live-apply guard chain that `build-artifact-cache` resolves to canonical service `docker_build`.
- After this branch was synchronized with the latest `origin/main`, the exact-main replay from commit `b80cc3a886539bb467a7ed54b2e606180cd08f44` made ADR 0295 true on the live platform and increased the repo-derived warm set from the earlier branch-local `40` images to `41` images on current main.
