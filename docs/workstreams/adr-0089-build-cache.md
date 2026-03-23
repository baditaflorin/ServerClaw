# Workstream ADR 0089: Build Artifact Cache and Layer Registry

- ADR: [ADR 0089](../adr/0089-build-artifact-cache.md)
- Title: Persistent Docker layer, pip, apt, and Ansible collection caches on the build server for sub-20-second check runs
- Status: ready
- Branch: `codex/adr-0089-build-cache`
- Worktree: `../proxmox_florin_server-build-cache`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`, `adr-0083-docker-check-runner`
- Conflicts With: none
- Shared Surfaces: `docker/`, `config/`, `Makefile`, `roles/build_server/`

## Scope

- provision `apt-cacher-ng` on `build-lv3` via `roles/build_server/` (new sub-task in the existing build server role)
- configure BuildKit daemon on `build-lv3` with a 50 GB disk cache under `/opt/builds/.buildkit-cache/`
- add `pip-cache` Docker named volume to all Python check runner invocations in `scripts/remote_exec.sh`
- add Packer plugin cache mount to all Packer container invocations
- add Ansible Galaxy collection cache directory at `/opt/builds/.ansible/collections/` with SHA-gated install logic
- write `config/build-cache-manifest.json` — tracks image digests, cache sizes, last-warm date
- write Windmill workflow `warm-build-cache` — triggers on `main` merges affecting `docker/check-runners/`, `requirements.yml`, or `packer/`; also runs nightly at 03:00
- add `make warm-cache` target (triggers the Windmill workflow on demand)
- add `make cache-status` target (reads `config/build-cache-manifest.json` and prints cache health summary)
- add weekly `pip cache purge` and `apt-cacher-ng` size check to the Windmill maintenance workflow (ADR 0080)

## Non-Goals

- build-server NVMe provisioning or RAID configuration (hardware; done outside IaC)
- caching for production service Docker images (those use `registry.lv3.org` pull-through cache, which is a separate ADR)

## Expected Repo Surfaces

- updated `roles/build_server/tasks/main.yml` (apt-cacher-ng, BuildKit daemon, directory creation)
- updated `roles/build_server/defaults/main.yml` (cache paths, sizes)
- updated `scripts/remote_exec.sh` (pip-cache volume mount, Packer plugin cache mount, Galaxy cache logic)
- `config/build-cache-manifest.json` (initially empty; populated by first `warm-build-cache` run)
- Windmill script `config/windmill/scripts/warm-build-cache.py`
- Windmill script `config/windmill/scripts/build-cache-maintenance.py`
- updated `Makefile` (`warm-cache`, `cache-status`)
- `docs/adr/0089-build-artifact-cache.md`
- `docs/workstreams/adr-0089-build-cache.md`
- `workstreams.yaml`
- `docs/runbooks/configure-build-artifact-cache.md`
- `playbooks/build-artifact-cache.yml`
- `playbooks/services/build-artifact-cache.yml`
- `scripts/cache_status.py`

## Expected Live Surfaces

- `apt-cacher-ng` running on `build-lv3:3142` (verified via `curl http://build-lv3:3142/acng-report.html`)
- BuildKit daemon running on `build-lv3` with 50 GB cache allocated
- `make remote-lint` on a warm cache completes in < 18 s (measured; not estimated)
- Windmill `warm-build-cache` workflow is scheduled and has a successful run in its history

## Verification

- run `make remote-lint` twice; second run completes at least 4× faster than first (cache effectiveness)
- `make cache-status` shows non-zero cache sizes for all four cache components
- `config/build-cache-manifest.json` contains current image digests matching `registry.lv3.org`
- simulate cold cache (stop BuildKit daemon, clear pip-cache volume); first run completes within 10 min; second run < 18 s

## Merge Criteria

- all four cache components provisioned and verified (docker layers, pip, apt-cacher-ng, galaxy collections)
- `make remote-lint` warm-cache timing documented in `config/build-cache-manifest.json`
- `warm-build-cache` Windmill workflow runs without errors

## Notes For The Next Assistant

- apt-cacher-ng requires the Packer provisioner scripts to inject the proxy config before any `apt-get install`; verify this is in `base-hardening.sh` before running a Packer build
- The repo-side implementation is complete on this branch, including the `remote_exec.sh`, runner-manifest, and `validate_repo.sh` cache hooks that were previously deferred.
- Remaining work is the integration step only: merge from `main`, bump the repo version, and apply the cache host live so the timing-based verification and Windmill schedules can be marked true.
