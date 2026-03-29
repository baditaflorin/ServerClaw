# Docker Runtime Disk Pressure

## Purpose

Recover `docker-runtime-lv3` when `/` is full enough to break repo-managed
package refreshes, container builds, or runtime converges.

## When To Use It

Use this runbook when a live apply on `docker-runtime-lv3` starts failing with
symptoms such as:

- `df -h /` showing `100%` usage or only a few megabytes free
- `apt-get update` or package installation failing because cache writes cannot
  complete
- Docker builds or image pulls failing during `make converge-api-gateway` or
  `make converge-ops-portal`

This is an emergency recovery path. It is not a substitute for fixing the repo
automation and replaying the managed converge after the guest is healthy again.

## Recovery Steps

Run the cleanup on `docker-runtime-lv3` as `ops` with `sudo`:

```bash
df -h /
sudo apt-get clean
sudo rm -f /var/cache/apt/pkgcache.bin /var/cache/apt/srcpkgcache.bin
sudo journalctl --vacuum-size=500M
docker image prune -af
docker builder prune -af
df -h /
sudo apt-get update -o Acquire::Retries=0
```

## Observed Example

During the ADR 0244 exact-main replay on 2026-03-29:

- before cleanup, `/` on `docker-runtime-lv3` was `95G used / 57M free` and
  `100%`
- after cleaning apt caches, old journal data, Docker images, and Docker
  builder cache, `/` recovered to about `24G free` and `apt-get update`
  succeeded again

## After Recovery

Re-run the repo-managed live apply from the controller:

```bash
make converge-api-gateway
make converge-ops-portal
```

Record the cleanup and the successful replay in the live-apply receipt or the
owning workstream document so later integrations know why the replay was
initially blocked.
