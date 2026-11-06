#!/bin/bash
# Idempotent checker and installer for the stopgap swapfile of the 0mcp hypervisor (pve-0mcp): /swapfile-0mcp-stopgap, 32 GiB, on / (md2, ext4). Run as root ON the hypervisor;
# nothing is copied there, the script is streamed through ssh (README.md next to this file says why the swapfile exists, how to undo it and when to remove it):
#   ssh operator-bastion 'bash -s -- check' < install-host.sh          # read-only, the default; exit 0 / 2 / 3 below
#   ssh operator-bastion 'bash -s -- --apply' < install-host.sh        # the file and swapon, as it was added by hand on 2026-11-01 (a reboot drops it)
#   ssh operator-bastion 'bash -s -- --persist' < install-host.sh      # --apply, plus the /etc/fstab line (needs the owner's yes: it is a change on a production hypervisor)
#   ssh operator-bastion 'bash -s -- --remove' < install-host.sh       # swapoff, the fstab line and the file go (refuses while too much is swapped out)
# Idempotent: it recognises the live file (path, size, mode, owner, swap signature with the label `stopgap`) and only adds what is missing; a run that has nothing to do changes nothing
# and makes no backup. What it refuses, and why:
#   - any machine other than pve-0mcp (hostname debian-base-template and a Proxmox node of that name); not root; a missing tool;
#   - creating the file on anything but ext4 (a swapfile with holes or copy-on-write is unsafe), or when / would keep less than 200 GB free after the 32 GiB file;
#   - a file at the path that is not ours (another size or another signature, a symlink, not a regular file): it is never overwritten, removed or formatted;
#   - removing it while more is swapped out than half of MemAvailable (swapoff has to move every page back into RAM first).
# Never `swapoff -a` and never touches /dev/md0 (the 4 GiB swap partition), other fstab lines or any VM. /etc/fstab is only rewritten after the candidate has been read back with findmnt,
# the old one is kept as /etc/fstab.bak-swap-<UTC time>, and the result is read back again (the backup is restored if it does not match).
# Exit codes: 0 everything as wanted (check) or done (the other verbs); 1 refused or invalid; 2 check: usable now but not persisted (no fstab line: a reboot drops it); 3 check: not as wanted.
# Sourcing this file only defines the functions and variables; the tests source it, point the variables at a fake host and call main. Nothing runs unless it is executed.
set -euo pipefail

SWAPFILE=/swapfile-0mcp-stopgap
SIZE=32G
SIZE_BYTES=34359738368
LABEL=stopgap
MIN_FREE_BYTES=200000000000
FSTYPE_WANTED=ext4
HOST_WANTED=debian-base-template
PVE_NODES=/etc/pve/nodes
FSTAB=/etc/fstab
PROC_SWAPS=/proc/swaps
PROC_MEMINFO=/proc/meminfo
FSTAB_OPTIONS=sw,nofail
LINE="$SWAPFILE none swap $FSTAB_OPTIONS 0 0"
TOOLS="fallocate mkswap swapon swapoff blkid findmnt df stat awk cmp"

tmp=""
new=""

# stdin: an fstab; stdout: the same fstab with the swapfile line as wanted. No line for $SWAPFILE yet: $LINE is appended. A line that already says exactly that (any spacing) is printed byte
# for byte, so a second run changes nothing; another line for the same file is replaced by $LINE (and a second one dropped). A commented line, or another file, is never matched.
fstab_with_swap() {
  awk -v path="$SWAPFILE" -v opts="$FSTAB_OPTIONS" -v line="$LINE" '
    $1 == path && $3 == "swap" {
      if (!found) {
        found = 1
        if ($2 == "none" && $4 == opts && ($5 == "" || $5 == "0") && ($6 == "" || $6 == "0")) print; else print line
      }
      next
    }
    { print }
    END { if (!found) print line }
  '
}

# stdin: an fstab; stdout: without any line for $SWAPFILE (only that file: /dev/md0 and the rest stay)
fstab_without_swap() {
  awk -v path="$SWAPFILE" '!($1 == path && $3 == "swap")'
}

say() { echo "install-host.sh: $*"; }
die() { echo "install-host.sh: $*" >&2; exit 1; }

usage() {
  cat <<EOF
usage: install-host.sh [check | --apply | --persist | --remove | --help]
  check      read-only report of $SWAPFILE (the default); exit 0 as wanted, 2 not persisted, 3 not as wanted
  --apply    create the $SIZE file if it is missing, make it swap, swapon (what was done by hand on 2026-11-01; a reboot drops it)
  --persist  --apply, then the line "$LINE" in $FSTAB (backup first)
  --remove   swapoff, drop the fstab line, delete the file (refuses while more than half of MemAvailable is swapped out)
EOF
}

cleanup() {
  if [ -n "$tmp" ]; then rm -f "$tmp"; fi
  if [ -n "$new" ]; then rm -f "$new"; fi
}

# ───────────────────────────── guards ─────────────────────────────

guard_host() {
  local host t
  [ "$(id -u)" = 0 ] || die "run as root"
  host=$(hostname)
  [ "$host" = "$HOST_WANTED" ] || die "this is $host, not $HOST_WANTED (pve-0mcp): a 32 GiB swapfile on another machine would be wrong"
  [ -d "$PVE_NODES/$host" ] || die "$PVE_NODES/$host does not exist: this is not a Proxmox node"
  for t in $TOOLS; do command -v "$t" > /dev/null 2>&1 || die "$t is not installed"; done
}

# ───────────────────────────── what is there (read-only) ─────────────────────────────

# sets F_EXISTS F_TYPE F_LABEL F_UUID F_SIZE F_MODE F_OWNER F_OK ACTIVE USED_KIB PERSISTED HAS_LINE; none of it changes anything
read_state() {
  local sig
  F_EXISTS=0 F_TYPE="" F_LABEL="" F_UUID="" F_SIZE="" F_MODE="" F_OWNER="" F_OK=0 ACTIVE=0 USED_KIB=0 PERSISTED=0 HAS_LINE=0
  if [ -e "$SWAPFILE" ] || [ -L "$SWAPFILE" ]; then
    F_EXISTS=1
    if [ -f "$SWAPFILE" ] && [ ! -L "$SWAPFILE" ]; then
      F_SIZE=$(stat -c %s "$SWAPFILE")
      F_MODE=$(stat -c %a "$SWAPFILE")
      F_OWNER=$(stat -c %U:%G "$SWAPFILE")
      sig=$(blkid -o export "$SWAPFILE" 2> /dev/null || true)
      F_TYPE=$(printf '%s\n' "$sig" | sed -n 's/^TYPE=//p')
      F_LABEL=$(printf '%s\n' "$sig" | sed -n 's/^LABEL=//p')
      F_UUID=$(printf '%s\n' "$sig" | sed -n 's/^UUID=//p')
      if [ "$F_SIZE" = "$SIZE_BYTES" ] && [ "$F_MODE" = 600 ] && [ "$F_OWNER" = root:root ] && [ "$F_TYPE" = swap ] && [ "$F_LABEL" = "$LABEL" ]; then F_OK=1; fi
    else
      F_TYPE=not-a-regular-file
    fi
  fi
  if awk -v p="$SWAPFILE" '$1 == p { f = 1 } END { exit !f }' "$PROC_SWAPS"; then
    ACTIVE=1
    USED_KIB=$(awk -v p="$SWAPFILE" '$1 == p { print $4 }' "$PROC_SWAPS")
  fi
  # PERSISTED: the one line as wanted is there; HAS_LINE: some line for the file is there (as wanted or not)
  if cmp -s <(fstab_with_swap < "$FSTAB") "$FSTAB"; then PERSISTED=1; fi
  if ! cmp -s <(fstab_without_swap < "$FSTAB") "$FSTAB"; then HAS_LINE=1; fi
}

mem_available_bytes() { echo $(($(awk '/^MemAvailable:/ { print $2 }' "$PROC_MEMINFO") * 1024)); }
fs_free_bytes() { df -B1 --output=avail "$1" | tail -n 1 | tr -d ' '; }
fs_type() { findmnt -n -o FSTYPE -T "$1"; }

gib() { echo "$(($1 / 1073741824)) GiB"; }

# ───────────────────────────── check ─────────────────────────────

cmd_check() {
  local verdict=0 dir free
  read_state
  dir=$(dirname "$SWAPFILE")
  free=$(fs_free_bytes "$dir") || die "cannot read the free space of $dir"
  say "$SWAPFILE on $HOST_WANTED"
  if [ "$F_EXISTS" = 0 ]; then
    say "  file       MISSING (a rebuilt host needs: install-host.sh --persist)"
    verdict=3
  elif [ "$F_OK" = 1 ]; then
    say "  file       ok       $(gib "$F_SIZE") ($F_SIZE bytes), mode $F_MODE, $F_OWNER, swap signature, label $F_LABEL, uuid $F_UUID"
  else
    say "  file       WRONG    type '$F_TYPE' label '$F_LABEL' size '$F_SIZE' (wanted $SIZE_BYTES) mode '$F_MODE' (wanted 600) owner '$F_OWNER' (wanted root:root); this script will not touch it unless it is a safe completion"
    verdict=3
  fi
  if [ "$ACTIVE" = 1 ]; then
    say "  active     ok       in $PROC_SWAPS, $((USED_KIB / 1024)) MiB used"
  else
    say "  active     MISSING  not in $PROC_SWAPS (after a reboot: install-host.sh --apply)"
    verdict=3
  fi
  if [ "$PERSISTED" = 1 ]; then
    say "  fstab      ok       $LINE"
  else
    say "  fstab      absent   a reboot drops the swapfile (install-host.sh --persist adds: $LINE)"
    if [ "$verdict" = 0 ]; then verdict=2; fi
  fi
  say "  info       $(gib "$free") free on $dir, MemAvailable $(gib "$(mem_available_bytes)")"
  return "$verdict"
}

# ───────────────────────────── the file and swapon ─────────────────────────────

make_file() {
  local dir free fstype need cand
  dir=$(dirname "$SWAPFILE")
  fstype=$(fs_type "$dir") || die "cannot read the filesystem type of $dir"
  [ "$fstype" = "$FSTYPE_WANTED" ] || die "$dir is $fstype, not $FSTYPE_WANTED: a swapfile with holes or copy-on-write is unsafe there; nothing was changed"
  free=$(fs_free_bytes "$dir") || die "cannot read the free space of $dir"
  need=$((SIZE_BYTES + MIN_FREE_BYTES))
  [ "$free" -ge "$need" ] || die "$dir has $free bytes free, creating $SIZE would leave less than $MIN_FREE_BYTES ($need needed); nothing was changed"
  cand="$SWAPFILE.new-$TS"
  [ ! -e "$cand" ] || die "$cand exists (a run that was cut off?): look at it and remove it; nothing was changed"
  tmp=$cand # only now: the cleanup at exit removes $tmp, and a leftover that is not ours must stay
  (umask 077 && fallocate -l "$SIZE_BYTES" "$tmp")
  chmod 600 "$tmp"
  mkswap -L "$LABEL" "$tmp"
  mv -f "$tmp" "$SWAPFILE"
  tmp=""
  say "created $SWAPFILE ($SIZE, label $LABEL)"
}

# the file exists but is not complete: only a safe completion is done, anything else is refused
complete_file() {
  [ "$F_EXISTS" = 1 ] && [ -f "$SWAPFILE" ] && [ ! -L "$SWAPFILE" ] || die "$SWAPFILE is not a regular file: not touching it"
  [ "$F_SIZE" = "$SIZE_BYTES" ] || die "$SWAPFILE is $F_SIZE bytes, not $SIZE_BYTES: not ours to resize; remove it by hand or run --remove if it is the stopgap"
  [ "$F_OWNER" = root:root ] || die "$SWAPFILE belongs to $F_OWNER, not root:root: not touching it"
  if [ -z "$F_TYPE" ]; then
    # right size, no signature at all: a run that was cut off between fallocate and mkswap
    chmod 600 "$SWAPFILE"
    mkswap -L "$LABEL" "$SWAPFILE"
    say "wrote the swap signature (label $LABEL)"
  elif [ "$F_TYPE" = swap ] && [ "$F_LABEL" = "$LABEL" ]; then
    if [ "$F_MODE" != 600 ]; then
      chmod 600 "$SWAPFILE"
      say "mode $F_MODE -> 600"
    fi
  else
    die "$SWAPFILE has type '$F_TYPE' label '$F_LABEL', not swap labelled $LABEL: not ours; nothing was changed"
  fi
}

cmd_apply() {
  read_state
  if [ "$F_EXISTS" = 0 ]; then
    make_file
  elif [ "$F_OK" = 1 ]; then
    say "$SWAPFILE already as wanted ($(gib "$F_SIZE"), label $F_LABEL)"
  else
    [ "$ACTIVE" = 0 ] || die "$SWAPFILE is in use and is not as wanted (type '$F_TYPE' label '$F_LABEL' size '$F_SIZE' mode '$F_MODE'): nothing was changed"
    complete_file
  fi
  read_state
  [ "$F_OK" = 1 ] || die "$SWAPFILE is still not as wanted after the run"
  if [ "$ACTIVE" = 1 ]; then
    say "already active ($((USED_KIB / 1024)) MiB used)"
  else
    swapon "$SWAPFILE"
    read_state
    [ "$ACTIVE" = 1 ] || die "swapon ran but $SWAPFILE is not in $PROC_SWAPS"
    say "swapon $SWAPFILE"
  fi
}

# ───────────────────────────── /etc/fstab ─────────────────────────────

# $1 = fstab_with_swap | fstab_without_swap. The candidate is made next to the real file (same owner and mode), read back with findmnt, only then renamed over it; the old one is kept
# (only when something changes), and the result is read back again.
rewrite_fstab() {
  local fn=$1 want opts
  new="$FSTAB.new-swap-$TS"
  cp -p "$FSTAB" "$new"
  "$fn" < "$FSTAB" > "$new"
  if cmp -s "$FSTAB" "$new"; then
    rm -f "$new"
    new=""
    say "$FSTAB already as wanted"
    return 0
  fi
  if [ "$fn" = fstab_with_swap ]; then want=$FSTAB_OPTIONS; else want=""; fi
  opts=$(findmnt --tab-file "$new" --fstab -n -o OPTIONS -S "$SWAPFILE" || true)
  [ "$opts" = "$want" ] || die "the candidate $FSTAB reads back as '$opts', wanted '$want'; $FSTAB was not changed"
  cp -p "$FSTAB" "$FSTAB.bak-swap-$TS"
  mv -f "$new" "$FSTAB"
  new=""
  say "$FSTAB changed (backup $FSTAB.bak-swap-$TS)"
  if command -v systemctl > /dev/null 2>&1; then systemctl daemon-reload; fi
  opts=$(findmnt --fstab -n -o OPTIONS -S "$SWAPFILE" || true)
  if [ "$opts" != "$want" ]; then
    cp -p "$FSTAB.bak-swap-$TS" "$FSTAB"
    if command -v systemctl > /dev/null 2>&1; then systemctl daemon-reload; fi
    die "$FSTAB reads back as '$opts', wanted '$want': the backup is back in place"
  fi
}

cmd_persist() {
  cmd_apply
  rewrite_fstab fstab_with_swap
  say "persisted: $(findmnt --fstab -n -o SOURCE,TARGET,FSTYPE,OPTIONS -S "$SWAPFILE")"
}

# ───────────────────────────── remove ─────────────────────────────

cmd_remove() {
  local used avail
  read_state
  if [ "$F_EXISTS" = 0 ] && [ "$ACTIVE" = 0 ] && [ "$HAS_LINE" = 0 ]; then
    say "$SWAPFILE is already absent (no file, not swap, no fstab line)"
    return 0
  fi
  if [ "$F_EXISTS" = 1 ]; then
    [ -f "$SWAPFILE" ] && [ ! -L "$SWAPFILE" ] || die "$SWAPFILE is not a regular file: not removing it"
    [ "$F_TYPE" = swap ] && [ "$F_LABEL" = "$LABEL" ] || die "$SWAPFILE has type '$F_TYPE' label '$F_LABEL', not swap labelled $LABEL: not ours; nothing was changed"
  fi
  if [ "$ACTIVE" = 1 ]; then
    used=$((USED_KIB * 1024))
    avail=$(mem_available_bytes)
    [ $((used * 2)) -le "$avail" ] || die "refusing: swapoff has to move $used bytes back into RAM and MemAvailable is $avail (the limit is half); nothing was changed. Wait, or free memory first"
    swapoff "$SWAPFILE" || die "swapoff $SWAPFILE failed; nothing else was changed"
    say "swapoff $SWAPFILE ($used bytes moved back)"
  fi
  rewrite_fstab fstab_without_swap
  if [ "$F_EXISTS" = 1 ]; then
    rm -f "$SWAPFILE"
    say "removed $SWAPFILE"
  fi
  say "undone: no $SWAPFILE file, not swap, no fstab line (the 4 GiB /dev/md0 swap is untouched)"
}

# ───────────────────────────── main ─────────────────────────────

main() {
  local verb=${1:-check}
  case "$verb" in
    -h | --help | help) usage; return 0 ;;
    check | --check | --apply | --persist | --remove) ;;
    *) usage >&2; return 1 ;;
  esac
  [ "$#" -le 1 ] || { usage >&2; return 1; }
  guard_host
  TS=$(date -u +%Y%m%dT%H%M%SZ)
  trap cleanup EXIT
  case "$verb" in
    check | --check) cmd_check ;;
    --apply) cmd_apply ;;
    --persist) cmd_persist ;;
    --remove) cmd_remove ;;
  esac
}

# runs when executed (bash install-host.sh ...) or streamed (bash -s -- ... < install-host.sh, where BASH_SOURCE is empty); not when sourced.
# This stays the LAST line: bash reads a streamed script from stdin, and a tool that read stdin while main runs would otherwise eat the rest of it.
if [ -z "${BASH_SOURCE[0]:-}" ] || [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
