#!/usr/bin/env bash
# idle-cache-volumes-trim.sh — remove named CACHE volumes that no container uses and that nothing has written to for days (called by docker-build-gc.sh).
#
# Why: agent sessions and CI steps mount named volumes as Go build and module caches (`docker run -v claude-gocache:/root/.cache/go-build`,
# `wgci-cache`, `ccr-gocache`, `go126-gomod`, ...). `docker volume prune` never removes a named volume and nothing else trimmed them: on 2026-10-19 the
# docker-build VM held 51 unused named volumes, 77 GB, of which 18 GB had not been written for 3 to 25 days (the largest live ones were 17, 11 and 7 GB).
# The root filesystem fell from 130 to 50 GB free in three days against the CI controller's line (woodpecker-load-controller@ci.0mcp stops scheduling at
# 10% free): FleetRootFilesystemFillsWithin14Days fired, and the same disk had already drained the 0mcp CI queue on 2026-10-12 and 2026-10-14.
#
# A volume is removed only when ALL of these hold:
#   - its name says it is a cache (cache, gocache, gomod: case-insensitive); every other named volume is left alone, whatever its age;
#   - no container, running or stopped, has it attached (`docker ps -a --filter volume=NAME`), and `docker volume rm` refuses an attached volume anyway;
#   - nothing in its data directory, down to two levels (a Go cache is 256 two-hex-digit directories that change on every write), was modified in the
#     last CACHE_VOLUME_IDLE_DAYS (default 3).
# A removed cache is only a slower first build. DRY_RUN=1 lists what would go. One failing removal never stops the others; the exit status is 0.
# CACHE_VOLUME_ROOT (default /var/lib/docker/volumes) is where `<name>/_data` live; tests point it at a temporary directory.
set -uo pipefail
IDLE_DAYS=${CACHE_VOLUME_IDLE_DAYS:-3}
ROOT=${CACHE_VOLUME_ROOT:-/var/lib/docker/volumes}
DOCKER=${DOCKER:-docker}
DRY=${DRY_RUN:-0}
case "$IDLE_DAYS" in ''|*[!0-9]*) echo "idle-cache-volumes-trim: CACHE_VOLUME_IDLE_DAYS must be a whole number of days, got '$IDLE_DAYS'"; exit 2;; esac

idle_hours() { # newest modification under $1/_data (two levels) as hours ago; prints nothing when the directory is missing
  python3 - "$1/_data" <<'PY'
import os, sys, time
d = sys.argv[1]
if not os.path.isdir(d):
    sys.exit(0)
newest = os.stat(d).st_mtime
try:
    for e in os.scandir(d):
        newest = max(newest, e.stat(follow_symlinks=False).st_mtime)
        if e.is_dir(follow_symlinks=False):
            try:
                for e2 in os.scandir(e.path):
                    newest = max(newest, e2.stat(follow_symlinks=False).st_mtime)
            except OSError:
                pass
except OSError:
    pass
print(int((time.time() - newest) // 3600))
PY
}

total_mb=0; removed=0; kept_recent=0; kept_used=0
vols=$($DOCKER volume ls -q 2>/dev/null | grep -iE 'cache|gocache|gomod' || true)
if [ -z "$vols" ]; then
  echo "idle-cache-volumes-trim: no cache volumes"
  exit 0
fi
for v in $vols; do
  if [ -n "$($DOCKER ps -a --filter "volume=$v" -q 2>/dev/null | head -1)" ]; then kept_used=$((kept_used + 1)); continue; fi
  h=$(idle_hours "$ROOT/$v")
  [ -n "$h" ] || continue
  if [ "$h" -lt $((IDLE_DAYS * 24)) ]; then kept_recent=$((kept_recent + 1)); continue; fi
  mb=$(du -sm "$ROOT/$v/_data" 2>/dev/null | cut -f1); mb=${mb:-0}
  if [ "$DRY" = 1 ]; then
    echo "idle-cache-volumes-trim: would remove $v (${mb} MB, idle ${h} h)"
    removed=$((removed + 1)); total_mb=$((total_mb + mb))
    continue
  fi
  if $DOCKER volume rm "$v" >/dev/null 2>&1; then
    echo "idle-cache-volumes-trim: removed $v (${mb} MB, idle ${h} h)"
    removed=$((removed + 1)); total_mb=$((total_mb + mb))
  else
    echo "idle-cache-volumes-trim: could not remove $v (in use?), left alone"
  fi
done
echo "idle-cache-volumes-trim: $([ "$DRY" = 1 ] && echo would-remove || echo removed) $removed volumes, ${total_mb} MB; kept $kept_recent recently written and $kept_used attached (idle limit ${IDLE_DAYS} days)"
exit 0
