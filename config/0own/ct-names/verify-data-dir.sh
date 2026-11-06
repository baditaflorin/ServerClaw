#!/usr/bin/env bash
# Run INSIDE the 0own runtime VM (660) as root, after prepare-data-disk.sh --apply and BEFORE the first ct-names deploy. Read-only: it changes
# nothing except one zero-byte probe file, created as the container uid and deleted at once. It exists because of one silent failure: if the
# data disk is not mounted (fstab says nofail, so the VM boots without it), docker would create /srv/ct-names/data on the ROOT disk as
# root:root; the container (uid 10001) then could not write, but a later "fix" by chown would put the store on the root disk shared with the
# keystore replica and about 50 pool workloads. This check makes that visible first. Exit 0 = every check passed, 1 = at least one failed.
#   verify-data-dir.sh
# The deploy reads the host path from CT_DATA_HOST_DIR, declared as extra_env in the repo's service.yaml (written into the deploy .env by the
# runner, not by hand); this script also prints what the .env says once the compose directory exists.
set -uo pipefail

MOUNT="${MOUNT:-/srv/ct-names}"
DATA="${DATA:-${MOUNT}/data}"
DATA_UID="${DATA_UID:-10001}"
DATA_GID="${DATA_GID:-10001}"
MIN_FREE_GB="${MIN_FREE_GB:-900}"          # the disk is a 1 TiB thin ceiling; below this something else is mounted there
FSTAB="${FSTAB:-/etc/fstab}"
COMPOSE_ENV_GLOB="${COMPOSE_ENV_GLOB:-/opt/services/*ct*names*/.env}"

fail=0
ok()   { echo "ok:   $*"; }
bad()  { echo "FAIL: $*" >&2; fail=1; }

if mountpoint -q "$MOUNT"; then ok "${MOUNT} is a mount point"; else bad "${MOUNT} is not a mount point: the disk is missing, a deploy would write the store to the root disk"; fi

root_src="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
data_src="$(findmnt -n -o SOURCE --target "$DATA" 2>/dev/null || findmnt -n -o SOURCE --target "$MOUNT" 2>/dev/null || true)"
fstype="$(findmnt -n -o FSTYPE --target "$DATA" 2>/dev/null || findmnt -n -o FSTYPE --target "$MOUNT" 2>/dev/null || true)"
if [ -n "$data_src" ] && [ "$data_src" != "$root_src" ]; then ok "data lives on ${data_src} (${fstype:-?}), not on the root filesystem ${root_src:-?}"; else bad "data would live on the root filesystem (${data_src:-unknown} vs ${root_src:-unknown})"; fi

if [ -d "$DATA" ]; then
  owner="$(stat -c '%u:%g' "$DATA")"; mode="$(stat -c '%a' "$DATA")"
  if [ "$owner" = "${DATA_UID}:${DATA_GID}" ]; then ok "${DATA} is owned ${owner}"; else bad "${DATA} is owned ${owner}, the container runs as ${DATA_UID}:${DATA_GID}"; fi
  case "$mode" in 750|700|770) ok "mode ${mode}" ;; *) bad "mode ${mode} (expected 750)" ;; esac
  probe="${DATA}/.verify-probe.$$"
  if command -v setpriv >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
    if setpriv --reuid "$DATA_UID" --regid "$DATA_GID" --clear-groups sh -c ': > "$1" && rm -f -- "$1"' _ "$probe"; then ok "uid ${DATA_UID} can create and delete a file there"; else bad "uid ${DATA_UID} cannot write to ${DATA}"; rm -f -- "$probe"; fi
  else
    echo "skip: no setpriv or not root, write probe not run"
  fi
else
  bad "${DATA} does not exist (prepare-data-disk.sh --apply creates it)"
fi

free_gb="$(df -BG --output=avail "$MOUNT" 2>/dev/null | tail -1 | tr -dc '0-9')"
if [ -n "$free_gb" ] && [ "$free_gb" -ge "$MIN_FREE_GB" ]; then ok "${free_gb} GiB free on ${MOUNT}"; else bad "${free_gb:-?} GiB free on ${MOUNT}, expected at least ${MIN_FREE_GB} (a 1 TiB thin disk)"; fi

if grep -E "[[:space:]]${MOUNT}[[:space:]]" "$FSTAB" 2>/dev/null | grep -q 'nofail'; then ok "fstab mounts ${MOUNT} with nofail"; else bad "no fstab line for ${MOUNT} with nofail"; fi

for f in $COMPOSE_ENV_GLOB; do
  [ -f "$f" ] || continue
  line="$(grep -E '^CT_DATA_HOST_DIR=' "$f" || true)"
  if [ "$line" = "CT_DATA_HOST_DIR=${DATA}" ]; then ok "${f} has ${line}"; else bad "${f} has '${line:-no CT_DATA_HOST_DIR}', expected CT_DATA_HOST_DIR=${DATA}"; fi
done

[ "$fail" = 0 ] && echo "All checks passed." || echo "Not ready: fix the FAIL lines before deploying." >&2
exit "$fail"
