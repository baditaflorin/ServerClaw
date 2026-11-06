#!/usr/bin/env bash
# Run ON THE 0own HYPERVISOR as root. Adds a dedicated, thin, IO-capped data disk (a ZFS volume) to the 0own runtime VM (660) for ct-names.
#   attach-data-disk.sh            plan only (default): prints what it would do, changes nothing
#   attach-data-disk.sh --apply    create the volume and attach it
#   attach-data-disk.sh --status   show the current VM disk lines
#   attach-data-disk.sh --undo     detach the disk (keeps the volume and its data; prints the destroy command, never runs it)
# Why a separate disk: its own filesystem and journal inside the VM (the keystore replica and the pool workloads keep theirs), a hard
# per-disk IO cap at the Proxmox layer, backup=0 (the first backup of a new disk is a full read), and one place to grow or remove.
set -euo pipefail

VMID="${VMID:-660}"
SLOT="${SLOT:-scsi1}"
SIZE_G="${SIZE_G:-1024}"                 # thin: nothing is reserved, the pool only gives blocks that are written
POOL="${POOL:-rpool/data}"
STORAGE="${STORAGE:-local-zfs}"
VOLBLOCKSIZE="${VOLBLOCKSIZE:-64k}"      # sequential append-only segments on a spinning mirror; 16k (the default) is for random database pages
SERIAL="${SERIAL:-CTNAMES0}"
MBPS_RD="${MBPS_RD:-30}"                 # IO budget, see README: sustained average is expected below 2 MB/s, these are ceilings
MBPS_WR="${MBPS_WR:-15}"
IOPS_RD="${IOPS_RD:-200}"
IOPS_WR="${IOPS_WR:-100}"
MIN_POOL_FREE_G="${MIN_POOL_FREE_G:-1500}"   # refuse when the pool has less free than this (PBS and the build worker can still grow into it)
BACKUP_DIR="${BACKUP_DIR:-/root/ct-names-backups}"

mode="plan"
case "${1:-}" in
  "") ;;
  --apply) mode="apply" ;;
  --status) mode="status" ;;
  --undo) mode="undo" ;;
  *) echo "usage: $0 [--apply|--status|--undo]" >&2; exit 2 ;;
esac

run() { if [ "$mode" = "apply" ] || [ "$mode" = "undo" ]; then echo "+ $*"; "$@"; else echo "would run: $*"; fi; }

if [ "$mode" = "status" ]; then
  qm config "$VMID" | grep -E "^(scsi|virtio|sata|unused|memory|balloon|cores)" || true
  exit 0
fi

if [ "$mode" = "undo" ]; then
  line="$(qm config "$VMID" | grep -E "^${SLOT}:" || true)"
  [ -n "$line" ] || { echo "nothing on ${SLOT} of VM ${VMID}"; exit 0; }
  case "$line" in *"serial=${SERIAL}"*) ;; *) echo "REFUSING: ${SLOT} is not the ct-names disk (serial ${SERIAL}): ${line}" >&2; exit 1 ;; esac
  echo "The guest must have stopped the service and unmounted the disk first (umount /srv/ct-names, fstab line removed). Detaching only; the volume and its data stay."
  mkdir -p "$BACKUP_DIR"; qm config "$VMID" > "${BACKUP_DIR}/qm-${VMID}.conf.pre-undo-$(date -u +%Y%m%dT%H%M%SZ)"
  run qm set "$VMID" --delete "$SLOT"
  echo "The volume is now 'unused'. To free the space later (this DELETES the data, a person decides): zfs destroy ${POOL}/<its vm-${VMID}-disk-N name>"
  exit 0
fi

qm status "$VMID" | grep -q "status: running" || { echo "REFUSING: VM ${VMID} is not running" >&2; exit 1; }
if qm config "$VMID" | grep -qE "^${SLOT}:"; then echo "REFUSING: ${SLOT} of VM ${VMID} is already in use (idempotent: nothing to do if it is the ct-names disk)" >&2; exit 1; fi
avail_g="$(zfs list -Hp -o avail "$POOL" | awk '{printf "%d", $1/1073741824}')"
echo "pool ${POOL}: ${avail_g} GiB available (minimum required: ${MIN_POOL_FREE_G})"
[ "$avail_g" -ge "$MIN_POOL_FREE_G" ] || { echo "REFUSING: the pool has too little free space for a new disk that can grow to ${SIZE_G} GiB" >&2; exit 1; }
echo "host IO pressure now: $(grep '^full' "${PSI_FILE:-/proc/pressure/io}" 2>/dev/null || echo unavailable)  (informational: creating a thin volume is metadata only)"

n=0
while zfs list -H -o name "${POOL}/vm-${VMID}-disk-${n}" >/dev/null 2>&1; do n=$((n+1)); done
vol="vm-${VMID}-disk-${n}"
opts="discard=on,iothread=1,ssd=1,backup=0,serial=${SERIAL},mbps_rd=${MBPS_RD},mbps_wr=${MBPS_WR},iops_rd=${IOPS_RD},iops_wr=${IOPS_WR}"

if [ "$mode" = "apply" ]; then mkdir -p "$BACKUP_DIR"; qm config "$VMID" > "${BACKUP_DIR}/qm-${VMID}.conf.pre-attach-$(date -u +%Y%m%dT%H%M%SZ)"; echo "backup of the VM config: ${BACKUP_DIR}"; fi
run zfs create -s -V "${SIZE_G}G" -o "volblocksize=${VOLBLOCKSIZE}" "${POOL}/${vol}"
if ! run qm set "$VMID" "--${SLOT}" "${STORAGE}:${vol},${opts}"; then
  echo "qm set failed; the empty volume ${POOL}/${vol} was created but is not attached. Remove it by hand if wanted: zfs destroy ${POOL}/${vol}" >&2; exit 1
fi
if [ "$mode" = "apply" ]; then
  qm config "$VMID" | grep -E "^${SLOT}:" || { echo "qm config does not show ${SLOT} after the set: check by hand" >&2; exit 1; }
  echo "Done. Next, inside the VM: prepare-data-disk.sh --apply (finds the disk by serial ${SERIAL})."
else
  echo "Plan only. Run again with --apply to do it."
fi
