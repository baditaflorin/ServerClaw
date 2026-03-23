# Configure Build Artifact Cache

## Purpose

ADR 0089 moves the expensive build-time downloads for the private build VM onto persistent cache surfaces:

- Docker layers via a dedicated BuildKit daemon
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

## Converge The Build Host

Run the dedicated playbook against the build guest:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/build-artifact-cache.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected host-side outcomes:

- `apt-cacher-ng` is active on `docker-build-lv3:3142`
- `lv3-buildkitd.service` is active and exposes `/run/buildkit/buildkitd.sock`
- `docker buildx inspect lv3-cache --bootstrap` succeeds
- Docker volume `pip-cache` exists
- the cache directories under `/opt/builds/` exist and are stable across reruns

## Validate The Host

Check the apt proxy:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m uri \
  -a 'url=http://127.0.0.1:3142/acng-report.html status_code=200' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the BuildKit daemon and builder:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'systemctl is-active lv3-buildkitd && docker buildx inspect lv3-cache --bootstrap >/dev/null' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the cache directories:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'ls -ld /opt/builds/.buildkit-cache /opt/builds/.packer.d /opt/builds/.ansible/collections' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Warm And Inspect The Manifest

The repo-side summary helper reads the canonical manifest:

```bash
python3 scripts/cache_status.py --manifest config/build-cache-manifest.json
```

The Windmill helper script can be run manually on a worker with the repo mounted at `/srv/proxmox_florin_server`:

```bash
python3 config/windmill/scripts/warm-build-cache.py
```

Current dependency note:

- `scripts/remote_exec.sh` and `config/check-runner-manifest.json` are owned by ADR 0082 and ADR 0083.
- Until those branches land, the warm-cache helper will record warnings and skip Docker image warming when the manifest is absent.

## Operational Notes

- Keep the BuildKit cache root on the build VM's fast local storage.
- Do not commit runtime cache contents; only the manifest belongs in git.
- The first full warm run is expected to be slow. The value is in subsequent reuse.
