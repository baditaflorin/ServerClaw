#!/bin/bash
# Idempotent installer of the off-host backup copy checker on the Docker host VM (VM 100, run as root ON the host):
#   tar -C config/0docker/fleet-backup-offhost-check -cf - . | ssh dockerhost 'd=$(mktemp -d) && tar -C $d -xf - && sudo bash $d/install.sh [--undo]; rm -rf $d'
# Validates first (python syntax, JSON, git, the sidecar's key files), keeps a copy of whatever it replaces (<file>.pre-<UTC time>), installs the tool, the config and four units,
# runs ONE real check before enabling the timers and refuses to go on when the repository cannot be read (exit code 1: wrong key, no network). A damaged or incomplete
# copy (exit code 2) is not an install failure: that is exactly what the check exists to report. --undo removes the units, the tool, the config and both textfiles.
set -euo pipefail
cd "$(dirname "$0")"
TS=$(date -u +%Y%m%dT%H%M%SZ)
TOOL=/usr/local/sbin/fleet-backup-offhost-check
CFGDIR=/etc/fleet-backup-offhost-check
CFG=$CFGDIR/config.json
UNITDIR=/etc/systemd/system
UNITS="fleet-backup-offhost-check.service fleet-backup-offhost-check.timer fleet-backup-offhost-deep.service fleet-backup-offhost-deep.timer"
PROMS="/var/lib/prometheus/node-exporter/fleet_backup_offhost.prom /var/lib/prometheus/node-exporter/fleet_backup_offhost_deep.prom"

if [ "${1:-}" = "--undo" ]; then
  systemctl disable --now fleet-backup-offhost-check.timer fleet-backup-offhost-deep.timer 2>/dev/null || true
  for u in $UNITS; do rm -f "$UNITDIR/$u"; done
  rm -f "$TOOL" $PROMS
  rm -rf "$CFGDIR"
  systemctl daemon-reload
  echo "undone: units, tool, config and both textfiles removed (backups named *.pre-* next to the old paths are kept)"
  exit 0
fi

command -v git >/dev/null || { echo "git is not installed" >&2; exit 1; }
python3 -c "import ast,sys; ast.parse(open('fleet_backup_offhost_check.py').read())"
python3 -c "import json,sys; c=json.load(open('config.json')); [c[k] for k in ('repo','branch','sources','textfile','deploy_key','known_hosts')]"
KEY=$(python3 -c "import json; print(json.load(open('config.json'))['deploy_key'])")
KH=$(python3 -c "import json; print(json.load(open('config.json'))['known_hosts'])")
[ -r "$KEY" ] && [ -r "$KH" ] || { echo "the sidecar's key files are not readable here: $KEY / $KH" >&2; exit 1; }

install -d -m 755 "$CFGDIR"
for f in "$TOOL" "$CFG" $(for u in $UNITS; do echo "$UNITDIR/$u"; done); do [ -f "$f" ] && cp -a "$f" "$f.pre-$TS" || true; done
install -m 755 fleet_backup_offhost_check.py "$TOOL"
install -m 644 config.json "$CFG"
for u in $UNITS; do install -m 644 "$u" "$UNITDIR/$u"; done
systemctl daemon-reload

set +e
"$TOOL" check
rc=$?
set -e
if [ "$rc" -eq 1 ]; then
  echo "the first check could not read the off-host repository: undoing" >&2
  bash "$0" --undo
  exit 1
fi
[ "$rc" -eq 2 ] && echo "NOTE: the first check found the copy damaged or incomplete (exit 2): the installation is fine, the copy is not" >&2

systemctl enable --now fleet-backup-offhost-check.timer fleet-backup-offhost-deep.timer >/dev/null 2>&1
echo "timers: $(systemctl is-active fleet-backup-offhost-check.timer) / $(systemctl is-active fleet-backup-offhost-deep.timer); next: $(systemctl list-timers fleet-backup-offhost-check.timer --no-legend | awk '{print $1, $2, $3}')"
grep -E '^fleet_backup_offhost_(check_ok|copy_timestamp_seconds|copy_parts|copy_bytes|copy_present)' /var/lib/prometheus/node-exporter/fleet_backup_offhost.prom | head -20
