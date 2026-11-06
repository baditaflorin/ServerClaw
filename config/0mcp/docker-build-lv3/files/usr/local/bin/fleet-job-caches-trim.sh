#!/usr/bin/env bash
# fleet-job-caches-trim.sh — keep the Go build cache INSIDE each fleet-job-cache-* docker volume under a size cap, also while a job uses the volume
# (called by docker-build-gc.sh, step 3d). The work is done by go-fleet-job's own program, vendored byte for byte as fleet-job-caches.sh (the README says
# where it comes from and how it is pinned and updated); this script only picks its arguments and an image for it, runs it, and says in a few lines what happened.
#
# Why: on 2026-10-31 and again on 2026-11-02 one such volume, fleet-job-cache-gucapi-gocache (the Go build cache of the go-url-categorizer-api CI and test
# jobs), went from 17 GiB (10-29) to 80 GiB at 1.8 to 2.8 GiB an hour and took the root from 69 to 94 % used; the CI load controller stops scheduling at
# 10 % free. The volume is in use most weekday hours, so idle-cache-volumes-trim.sh (whole volumes, idle for 3 days) never touches it and nothing bounded it.
#
# What it takes, and only that (the program's own rules, tested in go-fleet-job; the README has the evidence and what is not verified):
#   - only volumes called fleet-job-cache-*: every other volume, and every host directory, is never looked at;
#   - only inside a Go build cache (a directory whose README is the go tool's own): files, oldest first, until it is under CACHE_TRIM_MAX_GIB (default 20).
#     Never a directory, README or trim.txt, never a file used within the last hour, and while a container uses the volume never a file used within the
#     last CACHE_TRIM_BUSY_HOURS (default 12): so in a burst the cap can stay unmet (the line says cap_unmet=yes) instead of taking what a build may hold.
#     A trimmed entry is a cache miss, i.e. a rebuild (about 3 minutes once for the go-url-categorizer-api test suite) and nothing else. Module caches,
#     node_modules and everything else in a volume are counted and left alone;
#   - a volume is not removed here: whole-volume removal stays with idle-cache-volumes-trim.sh (3 idle days). The program does remove a volume that no
#     container refers to and nothing wrote to for CACHE_TRIM_UNUSED_DAYS (default 30) and has no switch to turn that off, so the number is ten times the
#     3-day rule: a backstop that can only act if that rule did not.
#
# The image. The program walks a volume in a throw-away container of a golang image (it needs GNU find) and never pulls one (docker --pull never). An image that
# no container uses is removed by every `docker image prune -a` whose age it exceeds: docker-build-gc.sh step 3 (every 4 hours) and fleet-docker-prune (daily)
# both use 168 hours, counted from the image's CREATION date, so a Go image that is already a week old upstream goes the first time no container uses it, and a
# prune with a shorter age takes it sooner (a session's `--filter until=24h` took golang:1.26 on 2026-11-02 at 22:46Z). So this step does not depend on one
# image being there: CACHE_TRIM_IMAGE is a list (default "golang:1.27 golang:1.26", the images CI runs), the first one on the host is used, and when none is,
# the first is pulled through the host's registry mirror (docker pull, 300 s at most, only with CACHE_TRIM_MIN_FREE_GIB (default 5, 0 = no check) free where
# docker keeps its images; CACHE_TRIM_PULL=0 turns the pull off; a dry run never pulls). The program itself still never pulls.
#
# When it cannot run it says so on a line that starts with WARNING (grep WARNING in the journal of docker-build-gc.service), and a full live run writes the
# textfile metric fleet_job_caches_trim.prom (CACHE_TRIM_PROM_DIR, default node_exporter's directory) as the other maintenance jobs of this host do
# (fleet_docker_prune.prom, wt_gc.prom, docker_network_gc.prom): last run time, last result (0 ran, 1 failed, 2 skipped), bytes freed, volumes still over the cap.
# DRY_RUN=1 changes nothing and lists what it would do (the volumes are mounted read-only; no metric). CACHE_TRIM_VOLUME=NAME limits it to the one volume
# fleet-job-cache-NAME (no metric either: a partial run must not overwrite the full run's). FLEET_JOB_CACHES_SH (default /usr/local/bin/fleet-job-caches.sh) is
# the program; tests point it elsewhere. Take the service's lock when running it by hand: flock -n /run/lock/docker-build-gc.lock /usr/local/bin/fleet-job-caches-trim.sh
# Exit status: 0 it ran; 1 a volume failed, docker did not answer or the report was not complete; 2 a setting is wrong (nothing was run); 3 skipped, nothing was
# looked at, because the program, docker, a Go image or room to pull one is missing. docker-build-gc.sh ignores the status: one failing step never stops the others.
set -uo pipefail
PROGRAM=${FLEET_JOB_CACHES_SH:-/usr/local/bin/fleet-job-caches.sh}
IMAGES=${CACHE_TRIM_IMAGE:-golang:1.27 golang:1.26}
PULL=${CACHE_TRIM_PULL:-1}
MIN_FREE_GIB=${CACHE_TRIM_MIN_FREE_GIB:-5}
PROM_DIR=${CACHE_TRIM_PROM_DIR:-/var/lib/prometheus/node-exporter}
MAX_GIB=${CACHE_TRIM_MAX_GIB:-20}
BUSY_HOURS=${CACHE_TRIM_BUSY_HOURS:-12}
UNUSED_DAYS=${CACHE_TRIM_UNUSED_DAYS:-30}
ONLY=${CACHE_TRIM_VOLUME:-}
DRY=${DRY_RUN:-0}
MIN_KEEP_SECONDS=3600 # the program's own minimum: nothing younger than an hour is ever taken

say() { printf 'fleet-job-caches-trim: %s\n' "$*"; }
refuse() { say "$*"; exit 2; }
whole() { case $1 in '' | *[!0-9]* | 0[0-9]*) return 1 ;; esac; [ "${#1}" -le 6 ]; }

whole "$MAX_GIB" && [ "$MAX_GIB" -ge 1 ] || refuse "CACHE_TRIM_MAX_GIB must be a whole number of GiB, at least 1, got '$MAX_GIB'"
whole "$BUSY_HOURS" && [ "$BUSY_HOURS" -ge 6 ] || refuse "CACHE_TRIM_BUSY_HOURS must be a whole number of hours, at least 6 (a build can hold a cache entry for an hour and a bit), got '$BUSY_HOURS'"
whole "$UNUSED_DAYS" && [ "$UNUSED_DAYS" -ge 4 ] || refuse "CACHE_TRIM_UNUSED_DAYS must be a whole number of days, at least 4 (whole volumes go after 3 idle days, by idle-cache-volumes-trim.sh; this step trims inside), got '$UNUSED_DAYS'"
whole "$MIN_FREE_GIB" || refuse "CACHE_TRIM_MIN_FREE_GIB must be a whole number of GiB (0 turns the check off), got '$MIN_FREE_GIB'"
case $DRY in 0 | 1) ;; *) refuse "DRY_RUN must be 0 or 1, got '$DRY'" ;; esac
case $PULL in 0 | 1) ;; *) refuse "CACHE_TRIM_PULL must be 0 or 1, got '$PULL'" ;; esac
read -r -a CANDIDATES <<<"$IMAGES"
{ [ "${#CANDIDATES[@]}" -ge 1 ] && [ "${#CANDIDATES[@]}" -le 6 ]; } || refuse "CACHE_TRIM_IMAGE must list one to six docker images, got '$IMAGES'"
for img in "${CANDIDATES[@]}"; do
  case $img in -* | *[!A-Za-z0-9_.:/@-]*) refuse "CACHE_TRIM_IMAGE has an element that is not a docker image reference: '$img'" ;; esac
done
if [ -n "$ONLY" ]; then
  case $ONLY in *[!A-Za-z0-9_.-]* | [-_.]*) refuse "CACHE_TRIM_VOLUME must be the part of a volume name after fleet-job-cache- (letters, digits, dot, underscore, dash), got '$ONLY'" ;; esac
fi

# a full live run reports to node_exporter's textfile directory; a dry run or one volume never overwrites that report, and a directory that is not there is no error
report() { # RESULT (0 ran, 1 failed, 2 skipped), BYTES FREED, VOLUMES STILL OVER THE CAP
  { [ "$DRY" = 0 ] && [ -z "$ONLY" ] && [ -d "$PROM_DIR" ]; } || return 0
  local tmp
  tmp=$(mktemp "$PROM_DIR/.fleet_job_caches_trim.XXXXXX" 2>/dev/null) || return 0
  cat >"$tmp" <<METRICS
# HELP fleet_job_caches_trim_last_run_timestamp_seconds Unix time of the last full run of docker-build-gc step 3d, whatever its result.
# TYPE fleet_job_caches_trim_last_run_timestamp_seconds gauge
fleet_job_caches_trim_last_run_timestamp_seconds $(date +%s)
# HELP fleet_job_caches_trim_last_result Result of that run: 0 it ran, 1 a volume failed or docker or the report was wrong, 2 skipped (the program, docker or a Go image is missing).
# TYPE fleet_job_caches_trim_last_result gauge
fleet_job_caches_trim_last_result $1
# HELP fleet_job_caches_trim_freed_bytes Bytes that run took out of the Go build caches.
# TYPE fleet_job_caches_trim_freed_bytes gauge
fleet_job_caches_trim_freed_bytes $2
# HELP fleet_job_caches_trim_volumes_over_cap Volumes that were still over the size cap after that run (the floor for a volume in use held the cap back).
# TYPE fleet_job_caches_trim_volumes_over_cap gauge
fleet_job_caches_trim_volumes_over_cap $3
METRICS
  { chmod 0644 "$tmp" && mv -f "$tmp" "$PROM_DIR/fleet_job_caches_trim.prom"; } || rm -f "$tmp"
  return 0
}
skip() { say "WARNING: SKIPPED: $*"; report 2 0 0; exit 3; }
free_gib() { # whole GiB free where docker keeps its images (/var/lib/docker when docker does not say); empty when df cannot tell
  local root
  root=$($T docker info --format '{{.DockerRootDir}}' 2>/dev/null)
  df -Pk "${root:-/var/lib/docker}" 2>/dev/null | awk 'NR == 2 { printf "%d", $4 / 1048576 }'
}

[ -x "$PROGRAM" ] || skip "$PROGRAM is not installed or not executable (go-fleet-job's program, vendored: see the README)"
command -v docker >/dev/null 2>&1 || skip "docker is not installed on this host"
T=""; command -v timeout >/dev/null 2>&1 && T="timeout 60"
TP=""; command -v timeout >/dev/null 2>&1 && TP="timeout 300"
IMAGE=""
for img in "${CANDIDATES[@]}"; do
  $T docker image inspect "$img" >/dev/null 2>&1
  rc=$?
  [ "$rc" = 124 ] && skip "docker did not answer within 60 s: nothing was looked at"
  if [ "$rc" = 0 ]; then IMAGE=$img; break; fi
done
if [ -z "$IMAGE" ]; then
  want=${CANDIDATES[0]}
  none="none of $IMAGES is on this host (an image that no container uses goes with the next prune whose age it exceeds, see the README)"
  [ "$DRY" = 1 ] && skip "$none; a live run would pull $want (CACHE_TRIM_PULL=$PULL): nothing was looked at"
  [ "$PULL" = 1 ] || skip "$none, and CACHE_TRIM_PULL=0: nothing was looked at"
  if [ "$MIN_FREE_GIB" != 0 ]; then
    free=$(free_gib)
    { [ -n "$free" ] && [ "$free" -ge "$MIN_FREE_GIB" ]; } || skip "$none, and ${free:-an unknown number of} GiB free where docker keeps its images is under CACHE_TRIM_MIN_FREE_GIB=$MIN_FREE_GIB, so $want was not pulled: nothing was looked at"
  fi
  pout=$($TP docker pull -q "$want" 2>&1)
  prc=$?
  [ "$prc" = 0 ] || skip "$none, and pulling $want failed (status $prc: $(printf '%s' "$pout" | tail -n 1 | tr -c 'A-Za-z0-9 ._,:()/-' ' ' | cut -c1-120)): nothing was looked at"
  say "NOTICE: none of $IMAGES was on this host: pulled $want"
  IMAGE=$want
fi

mode=prune
[ "$DRY" = 1 ] && mode=plan
[ "$DRY" = 1 ] && say "DRY RUN (plan: every volume is mounted read-only and nothing is changed)"
out=$("$PROGRAM" "$mode" $((UNUSED_DAYS * 86400)) $((MAX_GIB * 1073741824)) "$MIN_KEEP_SECONDS" "$IMAGE" "$ONLY" $((BUSY_HOURS * 3600)) 2>&1)
rc=$?
first=${out%%$'\n'*}
complete=1
case $out in *$'\n--summary--'*) ;; *) complete=0 ;; esac
if [ "$rc" != 0 ] || [ "$first" != "fleet-job-caches/1" ] || [ "$complete" != 1 ]; then
  say "WARNING: FAILED: the program ended with status $rc and did not give a complete fleet-job-caches/1 report; its last lines:"
  printf '%s\n' "$out" | tail -n 8 | cut -c1-200 | sed 's/^/  | /'
  report 1 0 0
  exit 1
fi

# one line per volume that changed, failed or still is over the cap (every volume for a dry run), then one line of totals; the lines that start with @ are for this script
summary=$(printf '%s\n' "$out" | awk -v dry="$DRY" -v cap="$MAX_GIB" -v busy="$BUSY_HOURS" -v unused="$UNUSED_DAYS" '
function mib(b) { return sprintf("%.0f", b / 1048576) }
function hours(s) { return sprintf("%.0f", s / 3600) }
function reset() {
  vol = ""; state = ""; kind = ""; vbytes = 0; tbytes = 0; tfiles = 0; cut = 0; capun = "no"
  rbytes = 0; rfiles = 0; err = ""; action = ""; result = ""
}
function flush(   line, show, warn) {
  if (vol == "") return
  nvol++
  line = sprintf("%s state=%s kind=%s size=%sMiB", vol, state, kind, mib(vbytes))
  show = 0; warn = ""
  if (dry) {
    if (action == "trim") { ntrim++; freed += tbytes }
    else if (action == "remove") { nremove++; freed += vbytes }
    else if (action == "skip") nskip++
    else nkeep++
    line = line " action=" action
    if (action == "trim") line = line sprintf(" would_free=%sMiB files=%.0f files_older_than=%sh", mib(tbytes), tfiles, hours(cut))
    if (action == "remove") line = line sprintf(" would_free=%sMiB", mib(vbytes))
    show = 1
  } else {
    if (result == "trimmed") { ntrim++; freed += rbytes; show = 1 }
    else if (result == "removed") { nremove++; freed += rbytes; show = 1 }
    else if (result == "failed") { nfail++; show = 1; warn = "WARNING: " }
    else if (result == "skipped") nskip++
    else nkeep++
    line = line " result=" result
    if (result == "trimmed" || result == "removed") line = line sprintf(" freed=%sMiB files=%.0f", mib(rbytes), rfiles)
    if (result == "failed") line = line " error=" err
  }
  if (capun == "yes") { line = line " cap_unmet=yes"; show = 1; nover++ }
  if (show) print "fleet-job-caches-trim: " warn line
  reset()
}
BEGIN { reset() }
/^volume=/ { flush(); vol = substr($0, 8); sub(/^fleet-job-cache-/, "", vol); next }
/^--summary--$/ { flush(); insum = 1; next }
{
  i = index($0, "=")
  if (i == 0) next
  k = substr($0, 1, i - 1); v = substr($0, i + 1)
  if (insum) { if (k == "docker") docker = v; if (k == "volumes") total = v; next }
  if (vol == "") next
  if (k == "state") state = v
  else if (k == "kind") kind = v
  else if (k == "bytes") vbytes = v + 0
  else if (k == "trim_bytes") tbytes = v + 0
  else if (k == "trim_files") tfiles = v + 0
  else if (k == "cut_age") cut = v + 0
  else if (k == "cap_unmet") capun = v
  else if (k == "removed_bytes") rbytes = v + 0
  else if (k == "removed_files") rfiles = v + 0
  else if (k == "error") err = v
  else if (k == "action") action = v
  else if (k == "result") result = v
}
END {
  flush()
  if (dry) printf "fleet-job-caches-trim: DRY RUN, nothing was changed: %d volumes, would trim %d and remove %d (%s MiB), %d left alone (in use and not a Go build cache), %d with nothing to take", nvol, ntrim, nremove, mib(freed), nskip, nkeep
  else printf "fleet-job-caches-trim: %d volumes: trimmed %d, removed %d (%s MiB freed), left alone %d, nothing to take %d, failed %d", nvol, ntrim, nremove, mib(freed), nskip, nkeep, nfail
  printf " (cap %s GiB, %s h floor while in use, whole volumes only after %s d idle)\n", cap, busy, unused
  if (docker != "ok") { print "fleet-job-caches-trim: WARNING: docker did not answer (docker=" docker "): nothing was done"; bad = 1 }
  if (total != "" && total + 0 != nvol) { print "fleet-job-caches-trim: WARNING: the report is incomplete: " nvol " volume blocks for volumes=" total; bad = 1 }
  printf "@freed %.0f\n@over %d\n", freed, nover
  if (nfail > 0 || bad) exit 1
  exit 0
}')
arc=$?
printf '%s\n' "$summary" | sed '/^@/d'
freed=$(printf '%s\n' "$summary" | sed -n 's/^@freed //p')
over=$(printf '%s\n' "$summary" | sed -n 's/^@over //p')
if [ "$arc" = 0 ]; then
  report 0 "${freed:-0}" "${over:-0}"
  exit 0
fi
report 1 "${freed:-0}" "${over:-0}"
exit 1
