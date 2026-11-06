#!/bin/bash
# Idempotent installer of the zram swap unit on the 0own hypervisor (run as root ON the host):
#   tar -C config/0own/zram-swap -cf - . | ssh 0own_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install.sh [--undo]; rm -rf $d'
# Validates the unit (systemd-analyze verify), keeps a copy of what it replaces in /root/zram-swap-backups (<file>.pre-<UTC time>, outside the systemd directories), installs the unit,
# removes the superseded hostconf drop-in 10-no-default-deps.conf (#560/#562: an empty After= in a drop-in cannot remove a line of the unit file), reloads systemd (NO restart: the running
# swap is untouched) and requires that the boot transaction has no ordering cycle afterwards: when it still has one, the previous unit and drop-in are put back and the exit code is 1.
# --undo puts back the newest backup of the unit and of the drop-in.
set -euo pipefail
cd "$(dirname "$0")"
TS=$(date -u +%Y%m%dT%H%M%SZ)
UNIT=/etc/systemd/system/zram-swap.service
DROPIN_DIR=/etc/systemd/system/zram-swap.service.d
DROPIN=$DROPIN_DIR/10-no-default-deps.conf
BK=/root/zram-swap-backups
cycles() { systemd-analyze verify default.target 2>&1 | grep -c -E 'ordering cycle|deleted to break' || true; }

if [ "${1:-}" = "--undo" ]; then
  u=$(ls -1t "$BK"/zram-swap.service.pre-* 2>/dev/null | head -n1 || true)
  d=$(ls -1t "$BK"/10-no-default-deps.conf.pre-* 2>/dev/null | head -n1 || true)
  [ -n "$u" ] || { echo "no backup of the unit in $BK" >&2; exit 1; }
  install -m 644 "$u" "$UNIT"
  if [ -n "$d" ]; then mkdir -p "$DROPIN_DIR"; install -m 644 "$d" "$DROPIN"; fi
  systemctl daemon-reload
  echo "undone: unit from $u${d:+, drop-in from $d}; boot ordering cycles now: $(cycles)"
  exit 0
fi

systemd-analyze verify "$PWD/zram-swap.service" 2>&1 | grep -v 'Special user nobody' && { echo "the unit does not verify" >&2; exit 1; } || true
mkdir -p "$BK"
[ -f "$UNIT" ] && cp -p "$UNIT" "$BK/zram-swap.service.pre-$TS"
[ -f "$DROPIN" ] && cp -p "$DROPIN" "$BK/10-no-default-deps.conf.pre-$TS"
before=$(cycles)
install -m 644 zram-swap.service "$UNIT"
rm -f "$DROPIN"; rmdir "$DROPIN_DIR" 2>/dev/null || true
systemctl daemon-reload
after=$(cycles)
if [ "$after" != 0 ]; then
  echo "the boot transaction still has $after ordering cycle line(s): rolling back" >&2
  bash "$0" --undo >&2 || true
  exit 1
fi
dd=$(systemctl show zram-swap.service -p DefaultDependencies --value)
aft=$(systemctl show zram-swap.service -p After --value)
case " $aft " in *" local-fs.target "*) echo "zram-swap.service is still After=local-fs.target" >&2; bash "$0" --undo >&2 || true; exit 1;; esac
echo "installed: DefaultDependencies=$dd After=[$aft]; ordering cycle lines $before -> $after"
echo "swap in use:"; swapon --show --noheadings || true
echo "rollback: bash $0 --undo   (backups in $BK)"
