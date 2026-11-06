#!/bin/bash
# Idempotent installer for the VM701 (infer-pg-primary) side of the shared-memory cap: /dev/shm limited to 10 GiB, persisted in /etc/fstab. Run as root on the VM:
#   scp install-vm.sh 0infer_pg_primary:/tmp/ && ssh 0infer_pg_primary 'sudo bash /tmp/install-vm.sh [--undo]'
# What it does (README.md next to this file says why):
#   1. refuses on any other machine, and when /dev/shm already holds more than the new size (a tmpfs cannot shrink below its content);
#   2. backs /etc/fstab up to /etc/fstab.bak-shm-<UTC time> (only when the file changes), then adds the `tmpfs /dev/shm` line, or sets size= on the one that is there;
#   3. `mount -o remount,size=10G /dev/shm`: live, no restart of anything; Postgres keeps running and its dynamic shared memory segments stay where they are;
#   4. validates with findmnt: the fstab entry carries the size and the live mount has exactly that many bytes.
# --undo removes the `tmpfs /dev/shm` line (the distribution default is back at the next boot) and remounts with size=50%, the kernel default for a tmpfs.
# The VM's memory (66560 MiB, no ballooning) is not touched here: it is a hypervisor setting, see README.md.
# Sourcing this file only defines the functions (the test uses fstab_with_shm_size); nothing runs unless it is executed.
set -euo pipefail

SIZE=10G
SIZE_BYTES=10737418240
LINE="tmpfs /dev/shm tmpfs rw,nosuid,nodev,size=${SIZE} 0 0"
FSTAB=/etc/fstab

# stdin: an fstab; stdout: the same fstab with the /dev/shm tmpfs line at $1 (a size such as 10G). No line yet: the canonical $LINE is appended. A line that is already
# there keeps its other options and gets size=$1 (a line that has it already is printed byte for byte, so a second run changes nothing).
fstab_with_shm_size() {
  awk -v size="$1" -v line="$LINE" '
    $1 == "tmpfs" && $2 == "/dev/shm" {
      found = 1
      n = split($4, opt, ",")
      have = 0
      for (i = 1; i <= n; i++) if (opt[i] == "size=" size) have = 1
      if (have) { print; next }
      out = ""; set = 0
      for (i = 1; i <= n; i++) {
        o = opt[i]
        if (o ~ /^size=/) { o = "size=" size; set = 1 }
        out = out (out == "" ? "" : ",") o
      }
      if (!set) out = out (out == "" ? "" : ",") "size=" size
      printf "%s %s %s %s %s %s\n", $1, $2, ($3 == "" ? "tmpfs" : $3), out, ($5 == "" ? "0" : $5), ($6 == "" ? "0" : $6)
      next
    }
    { print }
    END { if (!found) print line }
  '
}

# stdin: an fstab; stdout: without any /dev/shm tmpfs line
fstab_without_shm() {
  awk '!($1 == "tmpfs" && $2 == "/dev/shm")'
}

die() { echo "install-vm.sh: $*" >&2; exit 1; }

main() {
  local undo=0 ts opts
  [ "${1:-}" = "--undo" ] && undo=1
  [ "$(id -u)" = 0 ] || die "run as root"
  case "$(hostname)" in
    infer-pg-primary | infer-pg-primary.example.org) ;;
    *) die "this is $(hostname), not infer-pg-primary (VM701): a 10 GiB /dev/shm would be wrong on a machine that runs containers" ;;
  esac
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  new=$(mktemp "$FSTAB.new-shm.XXXXXX")
  trap 'rm -f "$new"' EXIT

  if [ "$undo" = 1 ]; then
    fstab_without_shm < "$FSTAB" > "$new"
  else
    used=$(df -B1 --output=used /dev/shm | tail -n 1 | tr -d ' ')
    [ "$used" -le "$SIZE_BYTES" ] || die "/dev/shm holds $used bytes, more than $SIZE: a tmpfs cannot shrink below its content; nothing was changed"
    fstab_with_shm_size "$SIZE" < "$FSTAB" > "$new"
  fi

  if cmp -s "$FSTAB" "$new"; then
    echo "$FSTAB already as wanted"
  else
    cp -p "$FSTAB" "$FSTAB.bak-shm-$ts"
    chmod --reference="$FSTAB" "$new"
    chown --reference="$FSTAB" "$new"
    mv -f "$new" "$FSTAB"
    echo "$FSTAB changed (backup $FSTAB.bak-shm-$ts)"
    systemctl daemon-reload
  fi

  if [ "$undo" = 1 ]; then
    ! grep -Eq '^tmpfs[[:space:]]+/dev/shm[[:space:]]' "$FSTAB" || die "a /dev/shm line is still in $FSTAB"
    mount -o remount,size=50% /dev/shm
    echo "undone: $(findmnt -n -o SIZE,OPTIONS /dev/shm)"
    return 0
  fi

  # findmnt --fstab reads the file back the way mount and systemd do: the entry must carry the size (the output goes into a variable: grep -q under pipefail can fail on SIGPIPE)
  opts=$(findmnt --fstab -n -o OPTIONS /dev/shm || true)
  case ",$opts," in
    *",size=$SIZE,"*) ;;
    *)
      if [ -e "$FSTAB.bak-shm-$ts" ]; then cp -p "$FSTAB.bak-shm-$ts" "$FSTAB"; fi
      die "findmnt does not read size=$SIZE from $FSTAB (got '$opts'; restored the backup if this run made one)"
      ;;
  esac
  mount -o remount,size="$SIZE" /dev/shm
  live=$(findmnt -n -b -o SIZE /dev/shm)
  [ "$live" = "$SIZE_BYTES" ] || die "/dev/shm is $live bytes, expected $SIZE_BYTES"
  echo "/dev/shm is $SIZE ($live bytes); $(findmnt -n -o OPTIONS /dev/shm)"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
