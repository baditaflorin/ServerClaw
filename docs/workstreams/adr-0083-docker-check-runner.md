# Workstream ADR 0083: Docker-Based Check Runner

- ADR: [ADR 0083](../adr/0083-docker-based-check-runner.md)
- Title: Containerised, versioned lint and validation toolchains running in parallel on the build server
- Status: ready
- Branch: `codex/adr-0083-docker-check-runner`
- Worktree: `../proxmox_florin_server-docker-check-runner`
- Owner: codex
- Depends On: `adr-0082-remote-build-gateway`
- Conflicts With: none
- Shared Surfaces: `docker/`, `config/`, `Makefile`, `registry.lv3.org`

## Scope

- create `docker/check-runners/` directory with four Dockerfiles: `ansible/`, `python/`, `infra/`, `security/`
- write `config/check-runner-manifest.json` — maps each check label to image, command, and timeout
- write `scripts/parallel_check.py` — launches multiple check containers concurrently and aggregates exit codes into a pass/fail summary with per-check timing
- add `make build-check-runners` target (builds all four images locally), `make push-check-runners` (pushes to `registry.lv3.org`)
- write Windmill workflow `platform-check-runner-rebuild` — triggers on Dockerfile changes merged to `main`, rebuilds and pushes, writes digest back to manifest
- add `.tool-versions` / `requirements.txt` pins in each Dockerfile directory

## Non-Goals

- running Molecule integration tests (those use ephemeral fixture VMs — ADR 0088)
- building production service images (those are defined per-service under `docker/<service>/`)

## Expected Repo Surfaces

- `docker/check-runners/ansible/Dockerfile` + `requirements.txt`
- `docker/check-runners/python/Dockerfile` + `requirements.txt`
- `docker/check-runners/infra/Dockerfile`
- `docker/check-runners/security/Dockerfile`
- `config/check-runner-manifest.json`
- `scripts/parallel_check.py`
- updated `Makefile` (`build-check-runners`, `push-check-runners`)
- Windmill script `config/windmill/scripts/check-runner-rebuild.py`
- `docs/adr/0083-docker-based-check-runner.md`
- `docs/workstreams/adr-0083-docker-check-runner.md`
- `workstreams.yaml`

## Expected Live Surfaces

- four check runner images live at `registry.lv3.org/check-runner/{ansible,python,infra,security}:<version>`
- `make remote-lint` uses these images (via `config/check-runner-manifest.json`)

## Verification

- `make build-check-runners` produces all four images with no build errors
- `scripts/parallel_check.py lint-ansible lint-yaml validate-schemas` completes in < 20 s on the build server with all three checks running concurrently
- image digests in `config/check-runner-manifest.json` match the actual published digests in `registry.lv3.org`

## Merge Criteria

- all four images build cleanly from a fresh Docker build (no cache)
- `ansible-lint --version` inside the ansible image matches the pinned version in the Dockerfile
- `parallel_check.py` returns a non-zero exit code if any individual check fails (regression guard)

## Notes For The Next Assistant

- pin base images to digests (not floating tags) in all Dockerfiles: `FROM debian:12-slim@sha256:...` — this is required by ADR 0068 image policy
- `trivy` in the security image requires a vulnerability database; add a `trivy db update` step to the Windmill rebuild workflow so the DB is current when the image is published
- set `--cpus=4` per container in `parallel_check.py` to prevent a single slow check from consuming all build server cores
