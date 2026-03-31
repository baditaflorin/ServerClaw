# Artifact Cache Runtime

## Purpose

This runbook covers the current artifact cache layout after ADR 0296:

- the dedicated `artifact-cache-lv3` guest hosts the private pull-through mirrors
- the build host consumes those mirrors for repeated upstream pulls
- the repo-derived warm set still comes from the committed image catalogs

ADR 0295 defines the shared cache-plane policy and ADR 0296 now makes the
dedicated `artifact-cache-lv3` VM the steady-state runtime.

## Converge The Dedicated Cache VM

Provision or replay the dedicated cache guest:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/artifact-cache-vm.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected outcomes:

- `artifact-cache-lv3` listens on `5001` through `5004`
- Docker on `artifact-cache-lv3` trusts `10.10.10.80:5001-5004` as insecure
  internal registries for local warm-up pulls
- `/opt/artifact-cache/seed-plan.json` exists on `artifact-cache-lv3`
- the four `artifact-cache-*` containers are running on the dedicated guest

## Repoint Build Consumers

Replay the build-host consumer wiring after the dedicated guest is healthy.
For production replays from the repository root, prefer the governed service
wrapper:

```bash
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache \
  env=production EXTRA_ARGS='-e bypass_promotion=true'
```

That path preserves the current redundancy, canonical-truth, promotion-bypass,
and ADR 0191 immutable-guest exception checks around `docker-build-lv3`.

For narrow role iteration or non-production dry runs, the direct playbook entry
remains useful:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/build-artifact-cache.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected outcomes:

- `docker-build-lv3` uses `10.10.10.80:5001-5004` as its private registry mirrors
- `docker buildx inspect lv3-cache --bootstrap` succeeds with the remote mirror-aware
  BuildKit config
- the old local `artifact-cache-*` containers are no longer running on
  `docker-build-lv3`

## Inspect The Warm Set

Render the current seed plan locally:

```bash
python3 scripts/artifact_cache_seed.py \
  --catalog config/image-catalog.json \
  --catalog config/check-runner-manifest.json \
  --catalog config/validation-gate.json \
  --mirror docker.io=10.10.10.80:5001 \
  --mirror ghcr.io=10.10.10.80:5002 \
  --mirror artifacts.plane.so=10.10.10.80:5003 \
  --mirror docker.n8n.io=10.10.10.80:5004
```

The output reports both:

- `seed_images`: refs that can be prewarmed through the managed mirrors
- `unsupported_images`: refs that still come from registries outside the
  current mirror set, such as the internal `registry.lv3.org`

## Verify The Runtime

Check the dedicated mirror listeners:

```bash
ansible -i inventory/hosts.yml artifact-cache-lv3 -m shell \
  -a 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.80:${port}/v2/" >/dev/null; done' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the generated plan file:

```bash
ansible -i inventory/hosts.yml artifact-cache-lv3 -m shell \
  -a 'jq ".seed_images | length" /opt/artifact-cache/seed-plan.json' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the managed BuildKit daemon and builder:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'systemctl is-active lv3-buildkitd && docker buildx inspect lv3-cache --bootstrap >/dev/null' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the build host now consumes the dedicated cache plane:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'docker buildx inspect lv3-cache --bootstrap >/dev/null && sudo cat /etc/docker/daemon.json' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operational Notes

- The previous phase-1 landing on `docker-build-lv3` is now only a rollback
  path; the intended runtime host is `artifact-cache-lv3`.
- Build and CI consumers move first. Other runtime guests should not adopt the
  cache plane until the dedicated VM has stayed stable long enough to justify
  the broader change.
- The governed production wrapper currently needs
  `ALLOW_IN_PLACE_MUTATION=true` because `docker-build-lv3` is still a
  documented ADR 0191 narrow exception while this consumer replay still mutates
  the build guest in place.
- The guest-side seed file lives at `/opt/artifact-cache/seed-plan.json`.
- The managed BuildKit unit on `docker-build-lv3` is `lv3-buildkitd.service`;
  there is no generic `buildkit.service` on that guest.
- Do not publish the mirror ports on the public edge.
