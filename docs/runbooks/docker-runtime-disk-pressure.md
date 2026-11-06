# Docker Runtime Disk Pressure

## Purpose

Recover `docker-runtime` when `/` is full enough to break repo-managed
package refreshes, container builds, or runtime converges.

## When To Use It

Use this runbook when a live apply on `docker-runtime` starts failing with
symptoms such as:

- `df -h /` showing `100%` usage or only a few megabytes free
- `apt-get update` or package installation failing because cache writes cannot
  complete
- Docker builds or image pulls failing during `make converge-api-gateway` or
  `make converge-ops-portal`
- MinIO uploads or Restic repository probes failing with messages such as
  `Storage backend has reached its minimum free drive threshold` or
  `restic ... snapshots --json timed out after 60 seconds` during
  `make converge-minio` or a live-apply backup trigger

This is an emergency recovery path. It is not a substitute for fixing the repo
automation and replaying the managed converge after the guest is healthy again.

## Recovery Steps

Run the cleanup on `docker-runtime` as `ops` with `sudo`:

```bash
df -h /
sudo apt-get clean
sudo rm -f /var/cache/apt/pkgcache.bin /var/cache/apt/srcpkgcache.bin
sudo journalctl --vacuum-size=500M
docker image prune -af
docker builder prune -af
docker ps -a --filter status=exited --size
# Remove only reviewed stopped scratch or superseded service containers if space is still critically low.
docker rm <container-id>...
df -h /
sudo apt-get update -o Acquire::Retries=0
```

If Docker image and builder pruning are not enough, review `docker ps -a` and
remove only clearly stopped scratch containers or superseded non-running service
containers. Re-check `docker system df` after each cleanup step so the recovery
stays deliberate.

If the Docker cleanup still leaves MinIO below its free-drive floor, remove
only repo-regenerable scanner caches before touching governed receipts or
service data:

```bash
sudo rm -rf /var/tmp/lv3-grype-db /var/tmp/lv3-security-posture /var/tmp/lv3-syft-cache
df -h /
```

## Observed Example

During the ADR 0244 exact-main replay on 2026-03-29:

- before cleanup, `/` on `docker-runtime` was `95G used / 57M free` and
  `100%`
- after cleaning apt caches, old journal data, Docker images, and Docker
  builder cache, `/` recovered to about `24G free` and `apt-get update`
  succeeded again

During the ADR 0292 Superset exact-main replay on 2026-04-01:

- before cleanup, `/` on `docker-runtime` fell to roughly `15M free`,
  MinIO verification uploads failed, and the live-apply Restic lock creation
  retried until timeout because MinIO refused writes below its free-drive floor
- after Docker image pruning and removal of the repo-regenerable scanner caches
  under `/var/tmp`, `/` recovered to about `2.1G free`, the Restic
  live-apply backup trigger succeeded again, and `make converge-minio`
  completed with `failed=0`

## After Recovery

Re-run the repo-managed live apply from the controller:

```bash
make converge-api-gateway
make converge-ops-portal
```

Record the cleanup and the successful replay in the live-apply receipt or the
owning workstream document so later integrations know why the replay was
initially blocked.

## The front-end run directories (`/home/ops/fe_runs`) and the janitor
On 2026-10-18 06:46Z the root disk of `docker-runtime` (VM 120, the host of the CI server, authelia and elasticsearch) reached 0% free: another agent session's front-end batteries start a new run dir
(a copy of a frontend plus `npm ci`, ~600 MB, `/home/ops/fe_runs/<name>/`) every couple of minutes and never clean up (84 GB in 141 dirs, +15 GB an hour).
- **What stops it now:** `fe-runs-janitor.timer` (every 30 minutes, `config/0mcp/docker-runtime/fe-runs-janitor/`, install with `install.sh` as root) removes ONLY the `node_modules` directories of idle run dirs
  (no file outside node_modules modified for 120 minutes, 30 with under 25% free, 10 with under 12% free; never a run dir mounted by a running container; symlinks are never followed). Run dirs, outputs
  and `/home/ops/fe-bp` are never touched. Metrics `fe_runs_janitor_*` (textfile), alerts `FeRunsJanitorStale` / `FeRunsJanitorMissing` in `fleet-disk.yml`. Dry run: `sudo FE_RUNS_DRY=1 /usr/local/sbin/fe-runs-janitor`, log `/var/log/fe-runs-janitor.log`.
- **Emergency by hand** (what was done on 2026-10-18): `docker pause` the containers mounting `/home/ops/fe_runs` (reversible), then run the janitor with `FE_RUNS_IDLE_MIN=10` (parallel `rm`, default I/O class: the idle class never finishes
  on that host), then `docker unpause`. A `du` of `/` takes minutes there: use targeted paths. The VM disk was also grown 256 -> 512 GB (`qm resize 120 scsi0 +256G` on the 0mcp host, then `growpart /dev/sda 1` and `resize2fs /dev/sda1` in the
  guest; the root partition is the last one of the cloud image). Note `discard=on` is only a PENDING setting of that VM until its next restart.

