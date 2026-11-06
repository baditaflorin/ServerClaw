#!/usr/bin/env bash
# Run INSIDE the 0own runtime VM (660) as root, after attach-data-disk.sh. Finds the ct-names data disk by its serial, makes one ext4
# filesystem on it (only if the disk is blank), mounts it on /srv/ct-names by UUID with nofail, and creates the data directory.
#   prepare-data-disk.sh            plan only (default)
#   prepare-data-disk.sh --apply    do it (idempotent: a disk that already carries the ct-names label is only mounted)
set -euo pipefail

SERIAL="${SERIAL:-CTNAMES0}"
MOUNT="${MOUNT:-/srv/ct-names}"
LABEL="${LABEL:-ctnames}"
DATA_UID="${DATA_UID:-10001}"            # the uid the container runs as; confirm against the service's Dockerfile before --apply
DATA_GID="${DATA_GID:-10001}"
FSTAB="${FSTAB:-/etc/fstab}"
BACKUP_DIR="${BACKUP_DIR:-/root/ct-names-backups}"

apply=0
case "${1:-}" in "") ;; --apply) apply=1 ;; *) echo "usage: $0 [--apply]" >&2; exit 2 ;; esac
run() { if [ "$apply" = 1 ]; then echo "+ $*"; "$@"; else echo "would run: $*"; fi; }

# virtio-scsi names the by-id link after the drive id (drive-scsi1), not the serial set with qm; the serial is only in sysfs, so look it up by lsblk
dev="$(lsblk -dpno PATH,SERIAL 2>/dev/null | awk -v s="$SERIAL" '$2==s {print $1; exit}' || true)"
[ -n "$dev" ] || dev="/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_${SERIAL}"
[ -e "$dev" ] || { echo "REFUSING: disk with serial ${SERIAL} not found (looked with lsblk, then ${dev}). Did attach-data-disk.sh run on the hypervisor? (a hot-plugged disk can need: echo '- - -' > /sys/class/scsi_host/host*/scan)" >&2; exit 1; }
real="$(readlink -f "$dev")"
if findmnt -rn -S "$real" >/dev/null 2>&1 && ! findmnt -rn -S "$real" -T "$MOUNT" >/dev/null 2>&1; then
  echo "REFUSING: ${real} is mounted somewhere other than ${MOUNT}" >&2; exit 1
fi
existing="$(blkid -o value -s LABEL "$real" 2>/dev/null || true)"
fstype="$(blkid -o value -s TYPE "$real" 2>/dev/null || true)"
if [ -n "$fstype" ] && [ "$existing" != "$LABEL" ]; then
  echo "REFUSING: ${real} already carries a ${fstype} filesystem that is not ours (label '${existing}'). Not touching it." >&2; exit 1
fi
echo "device: ${real} (serial ${SERIAL}), size $(lsblk -dn -o SIZE "$real"), rotational flag inside the VM: $(cat "/sys/block/$(basename "$real")/queue/rotational" 2>/dev/null || echo '?')"

if [ -z "$fstype" ]; then
  # nodiscard: the disk is a blank thin volume and the Proxmox IO caps count discarded bytes, so mkfs's default 1 TiB discard would take hours (hit on 2026-11-03)
  # -m 0: no root-reserved blocks on a data disk; lazy_itable_init: the format returns at once on a thin volume; -T largefile4: few, big files
  run mkfs.ext4 -q -L "$LABEL" -m 0 -T largefile4 -E lazy_itable_init=1,lazy_journal_init=1,nodiscard "$real"
else
  echo "filesystem already present (label ${LABEL}); not formatting"
fi

run mkdir -p "$MOUNT"
if [ "$apply" = 1 ]; then
  uuid="$(blkid -o value -s UUID "$real")"
  mkdir -p "$BACKUP_DIR"; cp -a "$FSTAB" "${BACKUP_DIR}/fstab.pre-ct-names-$(date -u +%Y%m%dT%H%M%SZ)"
  if ! grep -qE "[[:space:]]${MOUNT}[[:space:]]" "$FSTAB"; then
    # noatime: no write per read; nofail + device timeout: a missing disk must not stop the VM (and the keystore replica) from booting;
    # no online discard (it made the build worker's writes slow); trim by hand if ever needed
    printf 'UUID=%s %s ext4 defaults,noatime,nofail,x-systemd.device-timeout=30 0 2\n' "$uuid" "$MOUNT" >> "$FSTAB"
  fi
  systemctl daemon-reload
  mountpoint -q "$MOUNT" || mount "$MOUNT"
  mkdir -p "${MOUNT}/data"
  chown "${DATA_UID}:${DATA_GID}" "${MOUNT}/data"; chmod 0750 "${MOUNT}/data"
  findmnt -n "$MOUNT"; df -h "$MOUNT" | tail -1
  echo "Done. Bind-mount ${MOUNT}/data into the container (compose volume), not the whole disk."
else
  echo "would: add one fstab line by UUID (nofail), mount ${MOUNT}, create ${MOUNT}/data owned ${DATA_UID}:${DATA_GID} mode 0750"
  echo "Plan only. Run again with --apply to do it."
fi
