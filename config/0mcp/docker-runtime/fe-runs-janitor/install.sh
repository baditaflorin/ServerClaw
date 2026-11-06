#!/bin/bash
# Idempotent installer, run as root on docker-runtime (VM 120) from this directory. Backs up what it replaces (outside /etc/logrotate.d: logrotate includes every file there).
set -euo pipefail
cd "$(dirname "$0")"
B=/var/backups/fe-runs-janitor-$(date +%s); install -d -m 700 "$B"
for f in /usr/local/sbin/fe-runs-janitor /etc/systemd/system/fe-runs-janitor.service /etc/systemd/system/fe-runs-janitor.timer /etc/logrotate.d/fe-runs-janitor; do [ -f "$f" ] && cp -a "$f" "$B/" || true; done
install -m 755 fe-runs-janitor /usr/local/sbin/fe-runs-janitor
install -m 644 fe-runs-janitor.service fe-runs-janitor.timer /etc/systemd/system/
install -m 644 fe-runs-janitor.logrotate /etc/logrotate.d/fe-runs-janitor
logrotate -d /etc/logrotate.conf 2>&1 | grep -E "^error|: error" && { echo "logrotate configuration has errors" >&2; exit 1; } || true
systemctl daemon-reload
systemctl enable --now fe-runs-janitor.timer
echo "installed; backup in $B; first run: systemctl start fe-runs-janitor.service (FE_RUNS_DRY=1 /usr/local/sbin/fe-runs-janitor for a dry run)"
