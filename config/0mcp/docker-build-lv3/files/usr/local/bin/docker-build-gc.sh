#!/usr/bin/env bash
# docker-build-gc.sh — keep the 0mcp build worker (docker-build VM) from filling its root filesystem.
#
# Why: the Woodpecker load controller (CT108, woodpecker-load-controller@ci.0mcp) stops scheduling on this VM's agent when
# less than 10% of the disk is free and only resumes at 15% (20 consecutive 30 s samples). On 2026-10-12 the disk sat at
# 14.4-14.8% free and every CI pipeline of the 0mcp plane stayed `pending` for about two hours.
#
# What it does (all safe to repeat; run as root from docker-build-gc.timer):
#   1. wt-gc.sh on /home/ops/wt (idle, unused, clean and fully pushed repos only);
#   2. wt-gc.sh on the per-session workspaces, plain copies that nobody works in after a few days (idle >= 3 days);
#   3. docker build cache older than BUILD_CACHE_MAX_AGE_H (default 24) hours and unused images older than 7 days (recent layers stay for build speed);
#   3b. every BuildKit builder container's own cache (buildx_buildkit_*, buildkitd): `docker builder prune` only trims the default
#      builder, and on 2026-10-14 five builders held ~90 GB (one unused builder 32 GB) and drained the 0mcp CI queue again;
#      buildkit-cache-trim.sh keeps the most recent 8 GB in each;
#   3c. named CACHE volumes (Go build and module caches that sessions and CI steps mount: claude-gocache, wgci-cache, go126-gomod, ...) that no
#      container uses and nothing has written to for 3 days: idle-cache-volumes-trim.sh (2026-10-19: 77 GB of unused named volumes, 18 GB of them idle for
#      3 to 25 days, the root fell from 130 to 50 GB free in three days); every other named volume is still never touched;
#   3d. the Go build cache INSIDE each fleet-job-cache-* volume, which 3c never reaches because such a volume is in use most weekday hours (2026-10-31 and 11-02:
#      fleet-job-cache-gucapi-gocache 17 -> 80 GiB in two days at 1.8-2.8 GiB an hour, root 69 -> 94 % used): fleet-job-caches-trim.sh keeps each under 20 GiB with
#      go-fleet-job v0.5.0's own program (vendored as fleet-job-caches.sh), also while a job uses the volume but never taking a file used within 12 h; whole volumes stay with 3c;
#   4. containers stopped for more than 24 h, and anonymous volumes that no container uses (a `docker rm -f` without `-v`
#      orphans them: on 2026-10-13 two duplicate openbao-agent units did that every 5 s, 480,000 volumes and ~23 GB, and
#      the disk crossing the controller's 10% line stalled the 0mcp CI queue again). `docker volume prune` without --all
#      only removes anonymous volumes, never named ones;
#   5. journal vacuumed to 500 MB, files in /var/tmp older than 7 days and in /tmp older than 3 days.
# It never touches running containers, named volumes, or anything used in the last days; the exceptions are 3c (a cache volume no container has attached and
# nothing wrote to for 3 days goes whole) and 3d (Go build cache files not used for 12 h or more, inside a cache volume, also one that a job uses).
set -uo pipefail

say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }
free_pct() { df --output=pcent / | tail -1 | tr -dc 0-9; }
say "start: / ${used:-$(free_pct)}% used"

GC=/usr/local/bin/wt-gc.sh
if [ -x "$GC" ]; then
  [ -d /home/ops/wt ] && "$GC" --apply --root /home/ops/wt 2>&1 | grep -E '^(REMOVE|summary)' | tail -20
  S=/home/ops/builds/serverclaw-platform/.lv3-session-workspaces
  [ -d "$S" ] && "$GC" --apply --root "$S" --data-idle-days 3 2>&1 | grep -E '^(REMOVE|summary)' | tail -20
fi

if command -v docker >/dev/null 2>&1; then
  # 2026-10-21: 72 h let the default builder's cache reach 135 GB in three days under a CI wave (~6 GB/h, root at 80%, the controller's 10% line ~7 h away); `until=24h` freed 90 GB
  # at once and a 24 h cache still serves the rebuilds of a day. (Docker 29's --max-used-space / --reserved-space pruned nothing on this cache: tried, not used.)
  timeout 600 docker builder prune -f --filter "until=${BUILD_CACHE_MAX_AGE_H:-24}h" 2>&1 | tail -1
  timeout 900 docker image prune -a -f --filter until=168h 2>&1 | tail -1
  [ -x /usr/local/bin/buildkit-cache-trim.sh ] && timeout 3600 /usr/local/bin/buildkit-cache-trim.sh 2>&1 | tail -8
  [ -x /usr/local/bin/idle-cache-volumes-trim.sh ] && timeout 1800 /usr/local/bin/idle-cache-volumes-trim.sh 2>&1 | tail -8
  [ -x /usr/local/bin/fleet-job-caches-trim.sh ] && timeout 1800 /usr/local/bin/fleet-job-caches-trim.sh 2>&1 | tail -12
  timeout 300 docker container prune -f --filter until=24h 2>&1 | tail -1
  timeout 1800 docker volume prune -f 2>&1 | tail -1
fi

journalctl --vacuum-size=500M 2>&1 | tail -1
find /var/tmp -xdev -type f -mtime +7 -delete 2>/dev/null
find /tmp -xdev -type f -mtime +3 -delete 2>/dev/null
command -v fstrim >/dev/null 2>&1 && fstrim / >/dev/null 2>&1
say "done: / $(free_pct)% used"
