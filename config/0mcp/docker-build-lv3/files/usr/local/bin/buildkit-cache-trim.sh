#!/usr/bin/env bash
# buildkit-cache-trim.sh — cap the cache of every BuildKit builder container on this host (called by docker-build-gc.sh).
#
# Why: `docker builder prune` only trims the DEFAULT builder. buildx builders of the docker-container driver
# (buildx_buildkit_<name>0) and managed buildkitd containers keep their own cache in a state volume that nothing pruned. On
# 2026-10-14 five of them held ~90 GB on the 0mcp build worker (one builder nobody used any more held 32 GB), the disk fell
# under the CI controller's 10% line (woodpecker-load-controller@ci.0mcp) and the 0mcp CI queue stayed drained until it was
# trimmed by hand (25 GB -> 131 GB free).
#
# Each builder keeps its most recently used BUILDKIT_KEEP_MB (default 8000); BuildKit never removes cache a running build is
# using, so this is safe while builds run, and a trimmed cache is only a slower first build. A builder without buildctl, or one
# that is stopped, is skipped and reported; one failing never stops the others.
set -uo pipefail
KEEP_MB=${BUILDKIT_KEEP_MB:-8000}
DOCKER=${DOCKER:-docker}
T=""; command -v timeout >/dev/null 2>&1 && T="timeout 600"

names=$($DOCKER ps --format '{{.Names}}' 2>/dev/null | grep -E '^buildx_buildkit_|buildkitd' || true)
if [ -z "$names" ]; then
  echo "buildkit-cache-trim: no running BuildKit builder containers"
  exit 0
fi
for c in $names; do
  out=$($T $DOCKER exec "$c" buildctl prune --keep-storage "$KEEP_MB" 2>&1 | tail -1)
  echo "buildkit-cache-trim: $c keep=${KEEP_MB}MB -> ${out:-no output}"
done
exit 0
