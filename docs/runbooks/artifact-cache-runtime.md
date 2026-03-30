# Artifact Cache Runtime

## Purpose

This runbook covers the phase-1 artifact cache landing on `docker-build-lv3`:

- internal pull-through mirrors for repeated upstream container pulls
- a repo-derived warm set generated from the current image catalogs
- BuildKit mirror wiring for the build host

ADR 0295 defines the shared cache-plane policy and ADR 0296 keeps the
long-term target as a dedicated `artifact-cache-lv3` VM.

## Converge The Runtime

For production replays from the repository root, prefer the governed service
wrapper instead of a raw `ansible-playbook` call:

```bash
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=build-artifact-cache env=production EXTRA_ARGS='-e bypass_promotion=true'
```

That path preserves the current redundancy, canonical-truth, promotion-bypass,
and ADR 0191 immutable-guest exception checks around `docker-build-lv3`.

For narrow role iteration or non-production dry runs, the direct playbook entry
remains useful:

Run the existing build-cache converge playbook:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/build-artifact-cache.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected outcomes:

- `docker-build-lv3` listens on `5001` through `5004`
- `/opt/artifact-cache/seed-plan.json` exists on the guest
- `docker buildx inspect lv3-cache --bootstrap` succeeds with the mirror-aware
  BuildKit config

## Inspect The Warm Set

Render the current seed plan locally:

```bash
python3 scripts/artifact_cache_seed.py \
  --catalog config/image-catalog.json \
  --catalog config/check-runner-manifest.json \
  --catalog config/validation-gate.json \
  --mirror docker.io=10.10.10.30:5001 \
  --mirror ghcr.io=10.10.10.30:5002 \
  --mirror artifacts.plane.so=10.10.10.30:5003 \
  --mirror docker.n8n.io=10.10.10.30:5004
```

The output reports both:

- `seed_images`: refs that can be prewarmed through the managed mirrors
- `unsupported_images`: refs that still come from registries outside the
  current mirror set, such as the internal `registry.lv3.org`

## Verify The Runtime

Check the mirror listeners from the guest:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.30:${port}/v2/" >/dev/null; done' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the generated plan file:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'jq ".seed_images | length" /opt/artifact-cache/seed-plan.json' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the managed BuildKit daemon and builder:

```bash
ansible -i inventory/hosts.yml docker-build-lv3 -m shell \
  -a 'systemctl is-active lv3-buildkitd && docker buildx inspect lv3-cache --bootstrap >/dev/null' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operational Notes

- This phase intentionally lands on `docker-build-lv3` first so repeated image
  pulls stop blocking routine work.
- The dedicated cache VM remains a later integration step so this branch does
  not rewrite canonical fleet truth prematurely.
- The governed production wrapper currently needs
  `ALLOW_IN_PLACE_MUTATION=true` because `docker-build-lv3` is still a
  documented ADR 0191 narrow exception until ADR 0296 moves the cache plane
  onto a dedicated guest.
- The guest-side seed file lives at `/opt/artifact-cache/seed-plan.json`.
- The managed BuildKit unit on `docker-build-lv3` is `lv3-buildkitd.service`;
  there is no generic `buildkit.service` on that guest.
- Do not publish the mirror ports on the public edge.
