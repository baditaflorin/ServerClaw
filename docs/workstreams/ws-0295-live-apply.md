# Workstream ws-0295-live-apply: Live Apply ADR 0295 From Latest `origin/main`

- ADR: [ADR 0295](../adr/0295-shared-artifact-cache-plane-for-container-and-package-dependencies.md)
- Title: Replay the merged artifact-cache runtime on `docker-build-lv3` and record the first platform version where it is true
- Status: in_progress
- Implemented In Repo Version: 0.177.73
- Live Applied In Platform Version: N/A
- Implemented On: 2026-03-29
- Live Applied On: N/A
- Branch: `codex/ws-0295-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0295-live-apply`
- Owner: codex
- Depends On: `ws-0274-artifact-cache-plane`, `adr-0089-build-cache`, `adr-0153-distributed-resource-lock-registry`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0295`, `docs/workstreams/ws-0295-live-apply.md`, `docs/runbooks/artifact-cache-runtime.md`, `docs/runbooks/configure-build-artifact-cache.md`, `versions/stack.yaml`, `build/platform-manifest.json`, `README.md`, `receipts/live-applies/`

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
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `README.md`
- `receipts/live-applies/2026-03-29-adr-0295-shared-artifact-cache-plane-mainline-live-apply.json`

## Expected Live Surfaces

- `docker-build-lv3` listens on `10.10.10.30:5001-5004` for the repo-managed pull-through mirrors
- `/opt/artifact-cache/seed-plan.json` exists on `docker-build-lv3`
- `artifact-cache-docker-hub`, `artifact-cache-ghcr`, `artifact-cache-plane`, and `artifact-cache-n8n` are running on `docker-build-lv3`
- `docker buildx inspect lv3-cache --bootstrap` succeeds with the mirrored registry config still active

## Ownership Notes

- this workstream only claims the canonical live-apply replay from current `main`; the architecture and repo implementation stay with `ws-0274-artifact-cache-plane`
- `docker-build-lv3` is governed by ADR 0191 immutable guest replacement, so any in-place apply must remain a documented narrow exception in both the workstream notes and the receipt
- the resource lock for this replay should be taken on `vm:130` before mutation starts

## Planned Verification

- `make ensure-resource-lock-registry`
- `python3 scripts/resource_lock_tool.py acquire --resource vm:130 --holder agent:codex/ws-0295-live-apply --lock-type exclusive --ttl-seconds 7200 --context-id ws-0295-live-apply`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'`
- `ssh ... ops@10.10.10.30 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.30:${port}/v2/" >/dev/null; done; docker buildx inspect lv3-cache --bootstrap >/dev/null; test -f /opt/artifact-cache/seed-plan.json'`

## Current Notes

- `origin/main` already contains the ADR 0295 implementation surfaces from `ws-0274-artifact-cache-plane`; this workstream exists to make that merged truth live and to update the canonical platform state afterward.
- Before the replay, `docker-build-lv3` still had `apt-cacher-ng` and `lv3-buildkitd` active but no `artifact-cache-*` containers, no listeners on ports `5001-5004`, and no `/opt/artifact-cache/seed-plan.json`.
