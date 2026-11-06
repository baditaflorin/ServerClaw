# WS-20261102: the build VM's own GC trims the Go build caches inside the cache volumes

## Status

In review (branch `claude/build-gc-cache-trim`, ADR 0494 as for the other VM 130 work). Git only: nothing is installed on the VM and nothing is changed on any host. The staged apply plan, with the undo of each step, is in `config/0mcp/docker-build-lv3/README.md` ("Go build caches inside the cache volumes"); applying it is the owner's decision.

## Goal

One Go build cache volume of the 0mcp build VM, `fleet-job-cache-gucapi-gocache` (the Go build cache of the go-url-categorizer-api CI and test jobs), grew from 17 GiB (2026-10-29) to 80 GiB (10-31, and again 11-02 08:47Z) at 1.8 to 2.8 GiB an hour and took the root filesystem from about 69 % to 94 % used, against the CI load controller's line of 10 % free. It is in use most weekday hours, so the host's existing `idle-cache-volumes-trim.sh` (whole volumes, idle for 3 days) never touches it and nothing bounds its size. go-fleet-job v0.5.0 (2026-11-02) has the tested program that does (`fleet-job cache prune`), but nothing schedules it. The host's own 4-hourly `docker-build-gc` should call that program, rather than a second implementation of it, so the Go build cache inside such a volume stays under a size cap.

## Change

- `files/usr/local/bin/fleet-job-caches.sh`: go-fleet-job tag v0.5.0 (commit `c29b3ccf063902ec67dd795b3a97409f9d7353be`), `pkg/remote/caches.sh`, byte for byte, sha256 `aa3927be96de8fc46b64b5b854713d18bff976d66803c13721c9936c4e7c5265`; pinned in the README, `files.sha256` and a test, with the update recipe in the README.
- `files/usr/local/bin/fleet-job-caches-trim.sh`: the wrapper. Settings with refusals (`CACHE_TRIM_MAX_GIB` 20, `CACHE_TRIM_BUSY_HOURS` 12, `CACHE_TRIM_UNUSED_DAYS` 30, `CACHE_TRIM_IMAGE` `golang:1.26`), `DRY_RUN=1` (the program's `plan`: read-only mounts, nothing changes), `CACHE_TRIM_VOLUME` (one volume), `SKIPPED` lines when the program, docker or the image is missing, one line per volume that changed or failed and one line of totals.
- `files/usr/local/bin/docker-build-gc.sh`: step 3d right after 3c (guarded by `-x`, `timeout 1800`) and two comment edits (the header list and the closing sentence, which said the GC never touches named volumes).
- `files.sha256` (three entries: the changed GC script and the two new files), `README.md` (table row and a dated section: why, the design choice, settings, expected effect, the name gap, the staged apply plan with undo, the pin, what is not verified), `tests/test_docker_build_gc_cache_trim.py` (42 tests).

## Design choice

Vendor go-fleet-job's program and call it from the GC, not extend `idle-cache-volumes-trim.sh`. That script cannot see inside a volume (it removes a whole volume that no container has attached and whose top two directory levels were not written for 3 days); taking Go build cache files out by age and size, never what a running build may hold, is a different job that the program already does with its own tests (go-fleet-job reports 355 top-level tests and 210 mutations that each turn a test red; not re-run here). An extension would be a second implementation of the README signature check, the age profile and cut, the re-judging of each file as it is removed, the floor for volumes in use, docker's own refusal and the inspect-before-mount guard, and a fix in either would not reach the other. Vendoring keeps one implementation: the program stays byte-identical to its tag, and this repository's own code is the thin wrapper, with its own tests. Whole-volume removal stays with step 3c, which runs first in the same pass; the program's own limit is set to 30 days, ten times the 3-day rule, because it has no switch against removing a volume (a backstop that only acts if 3c did not).

## Verified (read-only, 2026-11-02)

- Live files equal the manifest before this change: `./verify-live.sh` said `0 file(s) differ or are missing`; `docker-build-gc.sh` (04e71d75...) and `idle-cache-volumes-trim.sh` (62816f1d...) on the VM have the checksums of the repository copies, and the GC's last run (08:26-08:28Z) shows steps 3b and 3c working (`idle-cache-volumes-trim: removed 0 volumes, 0 MB; kept 19 recently written and 2 attached`).
- Name-gap survey (08:58Z; `docker volume ls`, `docker ps -a --filter volume=`, `sudo -n du -sxm`; nothing mounted, nothing removed): 58 volumes, 21 whose name matches the 3c rule, 13 called `fleet-job-cache-*` (33.7 GiB, 2 in use); outside the prefix `gucapi-gocache` 10.5 GiB, `ukfin-gocache` 5.8, `fleet-job-gocache` 1.9, `ms-gocache` 0.9, three module caches and one empty volume, and the host directory `/home/ops/domainscope-lab/gocache` 25.7 GiB (in use, bind-mounted by sessions' containers), which neither 3c nor 3d reaches. The README has the table and who should move to the `fleet-job-cache-` prefix.
- The parent session's one-off `fleet-job cache prune --yes` at 08:53Z (defaults, volumes found idle) took `fleet-job-cache-gucapi-gocache` from 80.4 to 23.8 GiB and the root from 78 to 66 % used: 61.3 GiB, exit 0 in 27 s. It did not use `--busy-age`.
- `golang:1.26` is on the host (5 days old; `docker-build-gc.sh` step 3 prunes unused images older than 7 days, so the step checks for it and says `SKIPPED` when it is gone).

## Not in this change

- Nothing is installed or run on the VM, no volume or directory is removed, nothing outside the `fleet-job-cache-` prefix is trimmed.
- fleet-state `scripts/ct108/` still holds copies of `docker-build-gc.sh` and `idle-cache-volumes-trim.sh` (and their tests, `tests/test_idle_cache_volumes_trim.py`); the copy of the GC script there is now behind this directory. Which repository is the source of truth for the VM's scripts is a decision for the owner; this change does not touch fleet-state.
- No change to `docker-build-gc.service` or `.timer` (4-hourly, `flock -n`, `Nice=15`, idle I/O, `TimeoutStartSec=2h`).
- The 12 hour floor can keep the hot volume above the 20 GiB cap in a burst (the line says `cap_unmet=yes`); a shorter floor (6 h is the program's minimum) or a more frequent run is a decision, not made here.

## Verification

Offline only. `tests/test_docker_build_gc_cache_trim.py` and `tests/test_docker_build_lv3_config.py`: 45 passed on 0mcp_docker_build (Python 3.13.5, pytest 8.4.2, GNU find 4.10.0, mawk 1.3.4), including the tests that run the real vendored program under a fake docker against sparse-file caches; 35 passed and 7 skipped (the GNU-find ones) on a Mac. A sweep of 28 one-line breakages (defaults, refusals, protocol and exit checks, the GC wiring, a byte of the vendored file, a re-vendored program that also prunes docker) left no survivor. shellcheck 0.11.0 is clean on the wrapper, the GC script and the vendored file (as `sh`). Then the repository pre-push gate.

## Rollback

Revert the commit: nothing was installed. On the VM, once the plan has been applied: `chmod -x /usr/local/bin/fleet-job-caches-trim.sh` skips step 3d from the next run; the README lists the other undo steps.
