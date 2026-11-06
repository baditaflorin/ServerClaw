# WS-20261103: step 3d of the build VM's GC does not depend on one golang image

## Status

In review (branch `claude/build-gc-helper-image`, ADR 0494 as for the other VM 130 work). Git only: nothing is installed on the VM and nothing is changed on any host. Steps 0 to 3 of PR 657's staged plan were run on 2026-11-02 with the first wrapper, so the VM holds that wrapper (`fleet-job-caches-trim.sh` `cbe8c83345a4...`) and the changed `docker-build-gc.sh` is not installed: this change has to be re-copied (step 1 of the README's plan) before step 4.

## Goal

PR 657 added step 3d to `docker-build-gc.sh`: go-fleet-job's program trims the Go build caches inside the `fleet-job-cache-*` volumes in throw-away containers of a golang image, with `--pull never`. The wrapper's default image `golang:1.26` was missing from the host at 2026-11-02 23:10Z, so the wrapper said `SKIPPED` and exited 0: after step 4 the step would silently never run. The goal is a step that finds an image, or fetches one, or says loudly that it could not.

## Evidence (read-only, 2026-11-03)

- **The finding as handed over does not hold right now:** `golang:1.26` (`593dc3550e05`) is on the host again, with one container running on it, next to `golang:1.27` and `golang:1.27.3` (one image, `a301d0a60356`, four containers); all three were created 2026-10-28 03:15Z. The exposure is real and dated, though.
- **Two scheduled pruners, one rule:** `docker-build-gc.sh` step 3 (every 4 hours) and `fleet-docker-prune` (daily 04:30 + up to 30 minutes; ran 04:42Z on 11-03) both run `docker image prune -a ... --filter until=168h`, which goes by the image's creation date: every unused image created more than a week ago goes. The three golang tags cross that line at **11-04 03:15Z**; the GC runs at 04:23Z, when CI is quiet (on 11-03 it found no container, even a stopped one, on any cache-named volume).
- **An ad-hoc prune:** agent history shows a session on another Mac running `docker image prune -a -f --filter until=24h` on VM 130 at 22:46Z on 11-02 (the daemon log has four golang digests at 22:47Z): that explains why `golang:1.26` was missing at 23:10Z while `golang:1.27`, in use by 12 containers, was not.
- **The pull path:** the daemon's registry mirrors are `http://10.10.10.80:5001/` (LAN pull-through cache; `/v2/` answered 200 in 8 ms, `library/golang` is in it) and `https://mirror.gcr.io/`; the root has 120 GB free (79 % used).
- **Metrics precedent:** node_exporter's textfile directory `/var/lib/prometheus/node-exporter/` already holds `fleet_docker_prune.prom`, `wt_gc.prom` (written by the GC's own step 1) and `docker_network_gc.prom`; `config/prometheus/rules/fleet-disk.yml` has a staleness alert for the first.
- **What was run on 2026-11-02 (reported by the session that ran it):** steps 0 to 2 at about 23:10Z, step 3 at 23:23Z with `CACHE_TRIM_IMAGE=golang:1.27`: 33,183 MiB freed from `fleet-job-cache-gucapi-gocache` in 48 s (64.1 to 30.3 GiB, `cap_unmet=yes`, exit 0). On 11-03 07:19Z the VM's files were `fleet-job-caches.sh` aa3927be..., `fleet-job-caches-trim.sh` cbe8c833..., `docker-build-gc.sh` 04e71d75... (read-only `sha256sum`).

## Change (`config/0mcp/docker-build-lv3/`)

- `files/usr/local/bin/fleet-job-caches-trim.sh`: `CACHE_TRIM_IMAGE` is a list (default `golang:1.27 golang:1.26`, one to six), the first image on the host is used; when none is, the first is pulled (`docker pull -q`, 300 s at most) through the host's mirrors, only with `CACHE_TRIM_MIN_FREE_GIB` (default 5, 0 = no check) free where docker keeps its images, never in a dry run, and `CACHE_TRIM_PULL=0` turns it off. Every non-run line starts with `WARNING`; exit 3 for a skip (1: a volume failed or the report was incomplete; 2: a wrong setting); a full live run writes `fleet_job_caches_trim.prom` (last run time, last result 0/1/2, bytes freed, volumes still over the cap) into `CACHE_TRIM_PROM_DIR`.
- `files.sha256`: the wrapper's entry. The vendored program (`fleet-job-caches.sh`, aa3927be...) and `docker-build-gc.sh` are unchanged.
- `README.md`: the settings table, a paragraph "The image" with the evidence above, the staged plan rewritten for the state after 2026-11-02 (what was run with the first wrapper, re-copy the wrapper, step 4 only after), what is verified and what is not.
- `tests/test_docker_build_gc_cache_trim.py`: 59 tests (was 42): the list order, the pull and each of its guards, the `WARNING` lines and exit 3, the metric.

## Decisions

- **A bounded pull, not only a loud failure.** A list cannot help when all candidates go together (same creation date), and a loud failure leaves the hot volume (1.8 to 2.8 GiB an hour) untrimmed until some job pulls an image: on an idle night or weekend, hours. The mirror makes the pull cheap and rate-limit free; the cost is about 0.9 GB per pull, at most once per GC run, in idle hours, while upstream's image is more than 7 days old.
- **The prune is not changed and no pin container is added.** A stopped container that refers to the helper image would keep any `image prune -a` from taking it (docker's documentation), but it cannot be tried read-only and adds a long-lived object on the VM; the first step if the journal shows a pull on every run.
- **`golang:1.27.3` is not in the list:** it is a second tag of the same image, so it cannot exist when `golang:1.27` does not.
- **A metric yes, an alert not here.** The metric follows the host's own pattern; the alert is a rules-file change with its own promtool test and its own apply to the monitoring VM. A non-zero exit in the GC is not warranted: the GC ignores statuses on purpose and a failing unit would page for a skip that heals with the next pull; exit 3 serves manual runs.

## Not in this change

- Nothing is installed or run on any host. No image is pulled, removed or protected.
- `fleet-job cache ls/prune` and `gc --caches` (go-fleet-job) use fleet-job's configured image, `golang:1.26`, and fail with status 125 whenever it is missing (the `cache` verbs have no `--image` flag): the same cause, fixed in go-fleet-job (an `--image` flag or an image fallback) or by `"image": "golang:1.27"` in the Mac's fleet-job config. Not touched here.
- The alert rule for the metric. The fleet-state copies of the GC scripts.

## Verification

Offline only. `tests/test_docker_build_gc_cache_trim.py` and `tests/test_docker_build_lv3_config.py`: 62 passed on 0mcp_docker_build (Python 3.13.5, pytest 8.4.2, GNU find 4.10.0), including the tests that run the real vendored program under a fake docker; 55 passed and 7 skipped (the GNU-find ones) on a Mac. A sweep of 54 one-line breakages (defaults, refusals, the list order, each guard of the pull, exit codes, `WARNING`, the metric, the GC wiring, the vendored file) left no survivor. shellcheck 0.11.0 is clean. Then the repository pre-push gate.

## Rollback

Revert the commit: nothing was installed. On the VM the first wrapper stays in place until step 1 is run, and step 1 keeps a `.pre-image-fallback-*` copy of it.
