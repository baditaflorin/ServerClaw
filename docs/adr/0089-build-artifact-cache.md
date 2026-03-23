# ADR 0089: Build Artifact Cache and Layer Registry

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The build server (ADR 0082) and Docker check runner (ADR 0083) provide fast remote execution — but only if the required Docker images and build dependencies are already present on the build server. Without a cache strategy, every check run that requires a freshly-pulled image adds 2–8 minutes of network fetch time, negating the speed benefit of running remotely.

The current state:
- Docker images are pulled on demand from Docker Hub, GitHub Container Registry, and `registry.lv3.org`; no layer caching is configured
- `pip install` in Python check containers re-downloads packages every run because no pip cache is mounted
- Packer downloads its plugins from `releases.hashicorp.com` on every build
- `apt-get install` in Packer provisioner scripts pulls from Debian mirrors every template build
- `ansible-galaxy collection install` downloads collection dependencies from `galaxy.lv3.org` (or the public Galaxy) on every CI run

The cumulative effect: a full check run on a cold build server takes 6–12 minutes instead of 15–18 seconds.

## Decision

We will maintain a **multi-layer build artifact cache** on the build server, consisting of four components.

### 1. Docker layer cache (BuildKit inline cache)

All check runner image builds (`docker/check-runners/*/Dockerfile`) use BuildKit with inline cache export:

```bash
docker buildx build \
  --cache-from type=registry,ref=registry.lv3.org/check-runner/ansible:cache \
  --cache-to   type=registry,ref=registry.lv3.org/check-runner/ansible:cache,mode=max \
  -t registry.lv3.org/check-runner/ansible:2.17 \
  docker/check-runners/ansible/
```

The build server keeps a local BuildKit daemon with a 50 GB disk cache. Image layers that haven't changed since the last build are served from local cache in < 1 second.

### 2. pip download cache (persistent volume)

All Python containers mount a shared pip cache volume:

```bash
docker run --rm \
  -v pip-cache:/root/.cache/pip \
  -v /opt/builds/proxmox_florin_server:/workspace:ro \
  registry.lv3.org/check-runner/python:3.12 \
  pip install -r requirements.txt
```

`pip-cache` is a Docker named volume on the build server. After the first run, `pip install` resolves all packages from the local cache without a network fetch. Cache size is capped at 5 GB by a weekly `pip cache purge --size 5GB` job.

### 3. Packer plugin and apt-cacher cache

**Packer plugins** are cached under `/opt/builds/.packer.d/` on the build server, mounted into the `infra` check runner container:

```bash
docker run --rm \
  -v /opt/builds/.packer.d:/root/.packer.d \
  registry.lv3.org/check-runner/infra:latest \
  packer build templates/lv3-debian-base.pkr.hcl
```

**apt packages** during Packer provisioner runs are proxied through `apt-cacher-ng` running on `build-lv3:3142`. The Packer `shell` provisioner injects:
```bash
echo 'Acquire::http::Proxy "http://10.10.10.250:3142";' > /etc/apt/apt.conf.d/01proxy
```
Subsequent builds of any template that includes the same Debian packages pull from the local apt cache (~1 GB) rather than the Debian mirror.

### 4. Ansible Galaxy collection cache

`ansible-galaxy collection install` is invoked with a pinned path:

```bash
ansible-galaxy collection install \
  -p /opt/builds/.ansible/collections \
  -r requirements.yml \
  --no-deps  # deps resolved at build time; pinned in requirements.yml
```

`/opt/builds/.ansible/collections` is a persistent directory on the build server. Collections are only re-downloaded when the `requirements.yml` content changes (checked via SHA256 comparison before the galaxy call).

### 5. Cache manifest (`config/build-cache-manifest.json`)

Tracks the expected cache state for each component:

```json
{
  "docker_images": [
    {
      "image": "registry.lv3.org/check-runner/ansible:2.17",
      "digest": "sha256:...",
      "last_pulled": "2026-03-22T10:00:00Z",
      "size_mb": 380
    }
  ],
  "pip_cache_size_mb": 1240,
  "packer_plugins": ["github.com/hashicorp/proxmox@v1.4.1"],
  "ansible_collections": ["community.general:9.0.0", "lv3.platform:1.0.0"]
}
```

### Cache warming workflow

A Windmill workflow (`warm-build-cache`) runs:
- On every merge to `main` that changes `docker/check-runners/`, `requirements.yml`, or `packer/`
- Nightly at 03:00
- On demand via `make warm-cache`

The workflow pulls all images, runs a no-op `pip install`, pre-downloads Packer plugins, and updates `config/build-cache-manifest.json`.

### Cache eviction

| Cache | Max size | Eviction policy |
|---|---|---|
| Docker BuildKit | 50 GB | LRU automatic (BuildKit daemon) |
| pip | 5 GB | Weekly `pip cache purge --size 5GB` |
| apt-cacher-ng | 10 GB | Built-in LRU cache max |
| Packer plugins | 2 GB | Manual (update via `make update-packer-plugins`) |
| Ansible collections | 3 GB | Cleared and re-installed on `requirements.yml` change |

## Consequences

**Positive**
- Cold → warm cache transition: full `make remote-lint` drops from 8–12 min (image pull) to 8–18 s (from cache)
- `packer build` time drops from ~45 min (fresh apt download) to ~15 min (cached apt + plugins)
- Laptop is entirely insulated from network fetches for build tooling; all fetches happen on the build server's local NVMe
- `build-cache-manifest.json` provides observability: operators can see what is cached and when it was last refreshed

**Negative / Trade-offs**
- apt-cacher-ng is a new service on `build-lv3`; it must be provisioned as part of the build server role
- Cache warming workflow adds ~5 minutes of build server CPU/network work per `main` merge
- Docker volume and disk space management is an ongoing operational concern on `build-lv3`

## Implementation Notes

- This workstream branch now adds the repo-managed `build_server` role, a dedicated cache converge playbook, the cache manifest skeleton, the Windmill `warm-build-cache` helper, and an operator runbook for the cache host.
- Wiring the cache hooks into `scripts/remote_exec.sh`, `config/check-runner-manifest.json`, and the final `Makefile` targets is intentionally deferred until ADR 0082 and ADR 0083 finish, because those branches currently own those shared surfaces.
- Until ADR 0082 and ADR 0083 land, the cache warmer records warnings and skips Docker check-runner image warming when the upstream manifest is absent.

## Alternatives Considered

- **Nexus Repository Manager**: full-featured but heavyweight (~8 GB RAM); overkill for a homelab; apt-cacher-ng + pip cache + Docker BuildKit covers 95% of the use case
- **No cache, rely on fast bandwidth**: only works if build server has symmetric 1 Gbps internet; homelab typically has asymmetric residential ISP; apt mirror fetches are slow
- **Cache in MinIO**: MinIO can serve as an apt proxy (S3-compatible apt repo), but setup complexity exceeds the benefit of apt-cacher-ng

## Related ADRs

- ADR 0082: Remote build execution gateway (caching makes remote execution actually fast)
- ADR 0083: Docker check runner (images cached here; pip volumes mounted here)
- ADR 0084: Packer template pipeline (Packer plugins and apt cache)
- ADR 0088: Ephemeral fixtures (faster VM provisioning with cached Packer runs)
