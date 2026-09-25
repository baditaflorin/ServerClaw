# Artifact Cache Runtime

## Purpose

This runbook covers the current artifact cache layout after ADR 0296:

- the dedicated `artifact-cache` guest hosts the private pull-through mirrors
- the build host consumes those mirrors for repeated upstream pulls
- the repo-derived warm set still comes from the committed image catalogs

ADR 0295 defines the shared cache-plane policy and ADR 0296 now makes the
dedicated `artifact-cache` VM the steady-state runtime.

## Converge The Dedicated Cache VM

Provision or replay the dedicated cache guest:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/artifact-cache-vm.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected outcomes:

- `artifact-cache` listens on `5001` through `5004`
- Docker on `artifact-cache` trusts `10.10.10.80:5001-5004` as insecure
  internal registries for local warm-up pulls
- `/opt/artifact-cache/seed-plan.json` exists on `artifact-cache`
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
and ADR 0191 immutable-guest exception checks around `docker-build`.

For narrow role iteration or non-production dry runs, the direct playbook entry
remains useful:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/build-artifact-cache.yml \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected outcomes:

- `docker-build` uses `10.10.10.80:5001-5004` as its private registry mirrors
- `docker buildx inspect lv3-cache --bootstrap` succeeds with the remote mirror-aware
  BuildKit config
- the old local `artifact-cache-*` containers are no longer running on
  `docker-build`

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
  current mirror set, such as the internal `registry.example.com`

## Enable Private GHCR Upstream Pulls

The GHCR mirror starts in anonymous-upstream mode. It must remain that way
until the cache-owned package-read identity and its approved vault-renderer
delivery path are ready. Do not put a GitHub token in Ansible inventory,
Compose environment, a broker configuration, or a builder configuration.

To enable private package reads, the cache-only renderer must atomically write
this single full Docker Distribution configuration before the artifact-cache
role converges. It is mounted only by the separate private adapter; it is never
mounted by the public GHCR cache:

- host target: the fixed `/etc/artifact-cache/ghcr-proxy/config.yml` only
- parent directories: fixed `root:root`, non-symlink mode `0700`
- owner and group: `root:root`
- mode: `0400`
- type: regular file, never a symlink
- consumer: the private GHCR adapter only; it is bind-mounted read-only at
  `/etc/docker/registry/config.yml`

The only approved delivery is a root-side, cache-only render using a
short-lived `artifact-cache-ghcr-renderer` key against the cache-only vault
record `artifact_cache_ghcr_proxy_config`. It atomically replaces the target
file and revokes that key in the same operation. No API key may be retained on
VM180, mounted into a container, or placed in Ansible variables. The
`artifact_cache_runtime` role is only the consumer-side validator and mount
manager; it contains no secret-fetch path.

The rendered file is a complete registry configuration, not a Docker client
config or a raw PAT. It must declare `version: 0.1`, the GHCR upstream
`proxy.remoteurl: https://ghcr.io`, the private adapter's container listener
`0.0.0.0:5000`, the private storage settings used by this role, and the
dedicated cache reader's `proxy.username` and
`proxy.password`. The password is a narrowly scoped, cache-owned
package-read credential; it must never be the broker fallback credential or a
builder/VM credential.

The required shape is shown only as a non-secret schema:

```yaml
version: 0.1
log:
  level: warn
storage:
  filesystem:
    rootdirectory: /var/lib/registry
  delete:
    enabled: true
http:
  addr: 0.0.0.0:5000
proxy:
  remoteurl: https://ghcr.io
  username: <cache-only-package-reader>
  password: <cache-only-package-read-secret>
```

Set `artifact_cache_ghcr_private_packages_enabled: true` only after that
renderer receipt and file-mode check exist. The role validates the fixed path
without reading the content, requires a bridge-networked private listener
published only as `127.0.0.1:5005:5000`, and mounts the file only into the
`ghcr-private` service. It otherwise stops before Compose starts or changes a
private-GHCR cache. Its non-secret modification-time label makes Compose
recreate that service when the renderer atomically replaces the configuration,
so rotations take effect without touching the public `ghcr` adapter or other
cache adapters. Do not add `5005` to the VM firewall or configure any builder
or runtime consumer to use it.

Validation should use the exact immutable broker image digest through
`127.0.0.1:5005`. A failure must leave the private-GHCR flag disabled or the
cache converge blocked; do not bypass the cache with a direct `ghcr.io` pull
from the broker or either builder. Prove that the same request to
`10.10.10.80:5005` fails and that public `10.10.10.80:5002` remains anonymous.

## Verify The Runtime

Check the dedicated cache mirror listeners:

```bash
ansible -i inventory/hosts.yml artifact-cache -m shell \
  -a 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.80:${port}/v2/" >/dev/null; done' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the mirror listeners from the shared runtime consumer host:

```bash
ansible -i inventory/hosts.yml docker-runtime -m shell \
  -a 'for port in 5001 5002 5003 5004; do curl -fsS "http://10.10.10.80:${port}/v2/" >/dev/null; done' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the generated plan file:

```bash
ansible -i inventory/hosts.yml artifact-cache -m shell \
  -a 'jq ".seed_images | length" /opt/artifact-cache/seed-plan.json' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the managed BuildKit daemon and builder:

```bash
ansible -i inventory/hosts.yml docker-build -m shell \
  -a 'systemctl is-active lv3-buildkitd && docker buildx inspect lv3-cache --bootstrap >/dev/null' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Check the build host now consumes the dedicated cache plane:

```bash
ansible -i inventory/hosts.yml docker-build -m shell \
  -a 'docker buildx inspect lv3-cache --bootstrap >/dev/null && sudo cat /etc/docker/daemon.json' \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operational Notes

- The previous phase-1 landing on `docker-build` is now only a rollback
  path; the intended runtime host is `artifact-cache`.
- Build and CI consumers move first. Other runtime guests should not adopt the
  cache plane until the dedicated VM has stayed stable long enough to justify
  the broader change.
- The governed production wrapper currently needs
  `ALLOW_IN_PLACE_MUTATION=true` because `docker-build` is still a
  documented ADR 0191 narrow exception while this consumer replay still mutates
  the build guest in place.
- The guest-side seed file lives at `/opt/artifact-cache/seed-plan.json`.
- The managed BuildKit unit on `docker-build` is `lv3-buildkitd.service`;
  there is no generic `buildkit.service` on that guest.
- Consumer-side verification must include `docker-runtime`; a local listener
  on `docker-build` is not sufficient proof that the private cache plane is
  reachable from Windmill jobs and other runtime workloads.
- Do not publish the mirror ports on the public edge.
