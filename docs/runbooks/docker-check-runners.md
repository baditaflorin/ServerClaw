# Docker Check Runners

## Purpose

ADR 0083 moves heavyweight repository checks into pinned Docker images so operators and future CI workflows run the same toolchain with the same versions.

## Repository Surfaces

- check runner images: `docker/check-runners/`
- manifest: [config/check-runner-manifest.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/check-runner-manifest.json)
- local parallel executor: [scripts/parallel_check.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/parallel_check.py)
- local operator targets: [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile)
- rebuild workflow entry point: [config/windmill/scripts/check-runner-rebuild.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/check-runner-rebuild.py)

## Standard Commands

Build all four runner images locally:

```bash
make build-check-runners
```

On `docker-build-lv3`, the Make target automatically adds `--network host` so image rebuilds use the host resolver instead of the VM's flaky Docker bridge DNS path. Override with `CHECK_RUNNER_BUILD_NETWORK=` if you need Docker's default build network.

Run every manifest-defined check through the local Docker executor:

```bash
make run-checks
```

Run only a subset of checks:

```bash
make run-checks CHECKS="lint-yaml validate-schemas type-check"
```

Push locally-built images to the internal registry:

```bash
make push-check-runners
```

## Update Flow

1. Update the relevant Dockerfile or pinned version file under `docker/check-runners/`.
2. Rebuild the affected image locally with `make build-check-runners`.
3. Run `make run-checks CHECKS="..."` for the impacted check set.
4. Push the images with `make push-check-runners` once registry credentials are available.
5. Run the Windmill helper [config/windmill/scripts/check-runner-rebuild.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/check-runner-rebuild.py) from the build worker checkout to publish the updated image digests back into the manifest. The helper also switches to `--network host` automatically when it runs on `docker-build-lv3`.

## Notes

- `scripts/parallel_check.py` always mounts the current repo at `/workspace` and runs each requested check with `--cpus=4`.
- The manifest is intentionally check-oriented rather than image-oriented so future gates can compose checks without copying command definitions.
- Registry digests are written into the manifest only after the Windmill rebuild workflow publishes the images.
