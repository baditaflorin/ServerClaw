#!/bin/bash
# Idempotent installer for the PBS #2 per-group retention on infer-tier0 (VM704). Run as root from this directory:
#   tar -C config/0infer/tier0-pbs2 -cf - . | ssh 0infer_tier0 'd=$(mktemp -d) && tar -C $d -xf - && sudo bash $d/install.sh; rm -rf $d'
# Order: validate, back up what it replaces, install, dry run (changes nothing), enable the timer. The first real run is `sudo pbs-group-retention --apply`.
set -euo pipefail
cd "$(dirname "$0")"
TS=$(date -u +%Y%m%dT%H%M%SZ)
python3 -m py_compile pbs-group-retention pbs-prune-whatif.py && rm -rf __pycache__
python3 - <<'PY'
import importlib.machinery, importlib.util
l = importlib.machinery.SourceFileLoader("pgr", "pbs-group-retention"); s = importlib.util.spec_from_loader("pgr", l); m = importlib.util.module_from_spec(s); l.exec_module(m)
cfg = m.load_config("pbs-group-retention.json"); print("config ok:", [m.label(g) + f" keep {g['keep_last']}" for g in cfg["groups"]])
PY
[ -f /etc/pbs-group-retention.json ] && cp -a /etc/pbs-group-retention.json /etc/pbs-group-retention.json.bak-$TS
install -m 755 pbs-group-retention /usr/local/sbin/pbs-group-retention
install -m 755 pbs-prune-whatif.py /usr/local/sbin/pbs-prune-whatif                      # read-only: what would a retention change free? (see the README)
install -m 644 pbs-group-retention.json /etc/pbs-group-retention.json
install -m 644 pbs-group-retention.service pbs-group-retention.timer /etc/systemd/system/
systemctl daemon-reload
echo "--- dry run (nothing is deleted):"
/usr/local/sbin/pbs-group-retention || echo "dry run reported a problem (exit $?): read the lines above before enabling anything"
systemctl enable --now pbs-group-retention.timer
systemctl list-timers pbs-group-retention.timer --no-legend | cut -c1-110
