# Configure Build Artifact Cache

## Purpose

ADR 0089 moves the expensive build-time downloads for the private build VM onto persistent cache surfaces:

- Docker layers via a dedicated BuildKit daemon
- Docker upstream pulls via repo-managed pull-through mirror endpoints on `artifact-cache`
- Python downloads via the `pip-cache` Docker volume
- Packer plugins under `/opt/builds/.packer.d`
- Ansible collections under `/opt/builds/.ansible/collections`
- Debian package fetches via `apt-cacher-ng`

## Repository Surfaces

- playbook entrypoint: `playbooks/build-artifact-cache.yml`
- role: `roles/build_server/`
- cache manifest: `config/build-cache-manifest.json`
- operator summary helper: `scripts/cache_status.py`
- Windmill warming helper: `config/windmill/scripts/warm-build-cache.py`
- Windmill maintenance helper: `config/windmill/scripts/build-cache-maintenance.py`

## Converge The Build Host

For a governed production replay from the repository root, use:

```bash
: "${PLATFORM_IDENTITY_OVERLAY:?select the deployment identity.yml}"
: "${LV3_PROXMOX_HOST_ADDR:?set the deployment management host}"
: "${LV3_PROXMOX_HOST_PORT:?set the deployment SSH port}"
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'
```

The identity overlay and jump-host address/port must be the values for the
deployment being changed. The role fails before changing the host if the
resolved domain or identity prefix is still the generic `example` value.

The direct playbook entrypoint remains useful for role iteration and targeted
non-production convergence:

Run the direct playbook against the build guest:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/build-artifact-cache.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -e @"$PLATFORM_IDENTITY_OVERLAY"
```

Expected host-side outcomes:

- `apt-cacher-ng` is active on `docker-build:3142`
- the Docker daemon now points at `artifact-cache:5001-5004`
- the deployment-prefixed managed BuildKit systemd unit is active and exposes `/run/buildkit/buildkitd.sock`
- the deployment-prefixed Buildx builder bootstraps successfully
- Docker volume `pip-cache` exists
- the cache directories under `/opt/builds/` exist and are stable across reruns
- the old local `artifact-cache-*` containers are absent on `docker-build`

## Validate The Host

Check the apt proxy:

```bash
ansible -i inventory/hosts.yml docker-build -m uri \
  -a 'url=http://127.0.0.1:3142/acng-report.html status_code=200' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the BuildKit daemon and builder:

```bash
ansible -i inventory/hosts.yml docker-build -m shell \
  -a 'systemctl list-units --type=service "*-buildkitd.service" --no-legend && docker buildx ls' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the build host registry mirror wiring:

```bash
ansible -i inventory/hosts.yml docker-build -m shell \
  -a 'docker buildx inspect lv3-cache --bootstrap >/dev/null && sudo cat /etc/docker/daemon.json && ! docker ps --format "{{.Names}}" | grep -q "^artifact-cache-"' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the registry mirrors from the shared runtime consumer host:

```bash
ansible -i inventory/hosts.yml docker-runtime -m shell \
  -a 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.80:${port}/v2/" >/dev/null; done' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the cache directories:

```bash
ansible -i inventory/hosts.yml docker-build -m shell \
  -a 'ls -ld /opt/builds/.buildkit-cache /opt/builds/.packer.d /opt/builds/.ansible/collections' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Warm And Inspect The Manifest

The repo-side summary helper reads the canonical manifest:

```bash
python3 scripts/cache_status.py --manifest config/build-cache-manifest.json
```

The Windmill warm-cache helper can be run manually on a worker with the repo mounted at `/srv/proxmox-host_server`:

```bash
python3 config/windmill/scripts/warm-build-cache.py
```

The weekly cache-maintenance helper can also be run manually:

```bash
python3 config/windmill/scripts/build-cache-maintenance.py
```

## Operational Notes

- Keep the BuildKit cache root on the build VM's fast local storage.
- When replacing an explicitly inventoried legacy BuildKit container, pass its
  exact name through `build_server_buildkit_legacy_container_names` only after
  confirming there are no active builds. The role verifies the BuildKit image
  and both managed mounts before stopping it; the persistent cache directory
  is retained. It also stops the corresponding same-named systemd unit and
  disables non-canonical legacy units so they cannot respawn a daemon over the
  shared socket/cache. Because a systemd unit using Docker's `--rm` can remove
  its container as soon as the unit stops, the role reinspects each explicitly
  named container after the unit stop and only attempts a second stop if it is
  still present and running. It tolerates only the narrow race where a container
  disappears between that reinspection and `docker stop`; other inspection or
  stop errors still fail closed. The canonical unit is then reloaded and
  started with the managed container name. Set
  `build_server_buildkit_legacy_containers_idle_confirmed=true` with that
  explicit list; the role rejects an unconfirmed or duplicate list.
- The build guest is now a consumer of the dedicated cache plane, not the cache
  runtime host itself.
- The dedicated cache guest must be healthy before replaying this build-host
  path, otherwise the build daemon falls back to direct upstream access.
- The governed production wrapper currently requires
  `ALLOW_IN_PLACE_MUTATION=true` because this replay still mutates
  `docker-build` in place under the documented ADR 0191 exception.
- Verify the managed BuildKit daemon through the deployment-prefixed
  `*-buildkitd.service`; the guest does not ship a separate `buildkit.service`.
- Verify the cache plane from `docker-runtime` as well as `docker-build`
  so private consumer reachability is covered, not only local host listeners.
- Do not commit runtime cache contents; only the manifest belongs in git.
- The first full warm run is expected to be slow. The value is in subsequent reuse.
