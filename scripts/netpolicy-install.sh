#!/usr/bin/env bash
# Install (or update) the network policy drift job on CT108 from this checkout.
#
#   scripts/netpolicy-install.sh            # install files and units, do not enable the timer
#   scripts/netpolicy-install.sh --enable   # also enable the timer and run it once (READ-ONLY: it never changes a host)
#   scripts/netpolicy-install.sh --status   # show the timer, the last run and the metrics
#
# Only files identical to origin/main are installed: reviewed, merged code, never a working tree or an unmerged branch.
set -euo pipefail

mode="install"
case "${1:-}" in
  "") ;;
  --enable) mode="enable" ;;
  --status) mode="status" ;;
  *) echo "usage: $0 [--enable|--status]" >&2; exit 2 ;;
esac

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bastion="${NETPOLICY_BASTION:-0docker_bastion}"
ct() { ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- bash -c $(printf '%q' "$1")"; }

if [[ "$mode" == "status" ]]; then
  ct 'systemctl list-timers netpolicy-drift.timer --no-legend 2>&1 | cut -c1-120
      systemctl show netpolicy-drift.service -p Result -p ExecMainStatus | tr "\n" " "; echo
      journalctl -u netpolicy-drift.service -n 12 --no-pager -o cat | cut -c1-200
      ls -la /var/lib/prometheus-node-exporter/textfile/netpolicy_*.prom 2>&1 | cut -c1-140'
  exit 0
fi

files=(scripts/netpolicy.py scripts/netpolicy-run config/systemd/netpolicy-drift.service config/systemd/netpolicy-drift.timer)
git -C "$repo" fetch --quiet origin main
if ! git -C "$repo" diff --quiet origin/main -- "${files[@]}" || [[ -n "$(git -C "$repo" status --porcelain -- "${files[@]}")" ]]; then
  echo "refusing: these files differ from origin/main (unmerged or uncommitted changes): ${files[*]}" >&2
  echo "merge the change first, update this checkout to origin/main, then install." >&2
  exit 1
fi
url="$(git -C "$repo" remote get-url origin | sed -E 's#(https?://)[^/@]+@#\1#')"
case "$url" in https://github.com/*|git@github.com:*) ;; *) echo "origin is not a github.com URL: $url" >&2; exit 1 ;; esac

remote='set -euo pipefail
d=$(mktemp -d); trap "rm -rf \"$d\"" EXIT; tar -x -C "$d"; cd "$d"
python3 -m py_compile scripts/netpolicy.py
python3 scripts/netpolicy.py --help >/dev/null
bash -n scripts/netpolicy-run
python3 -c "import yaml" 
lib=/usr/local/lib/netpolicy
install -d -m 0755 "$lib"
[ -f "$lib/netpolicy.py" ] && cp -p "$lib/netpolicy.py" "$lib/netpolicy.py.bak-$(date -u +%Y%m%dT%H%M%SZ)"
install -m 0644 scripts/netpolicy.py "$lib/"
install -m 0755 scripts/netpolicy-run /usr/local/bin/netpolicy-run
install -m 0644 config/systemd/netpolicy-drift.service config/systemd/netpolicy-drift.timer /etc/systemd/system/
install -d -m 0755 /etc/fleet-runner
if [ ! -f /etc/fleet-runner/netpolicy.env ]; then
  printf "%s\n" "# Operator overrides for netpolicy-run." "export NETPOLICY_REPO_URL=$REPO_URL" > /etc/fleet-runner/netpolicy.env
  chmod 0644 /etc/fleet-runner/netpolicy.env
fi
systemctl daemon-reload
echo "installed into $lib"'

tar --no-xattrs --no-mac-metadata -C "$repo" -cf - "${files[@]}" \
  | ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- env REPO_URL=$(printf '%q' "$url") bash -c $(printf '%q' "$remote")"

if [[ "$mode" == "enable" ]]; then
  ct 'systemctl enable --now netpolicy-drift.timer
      systemctl start netpolicy-drift.service || true
      systemctl show netpolicy-drift.service -p Result -p ExecMainStatus | tr "\n" " "; echo
      journalctl -u netpolicy-drift.service -n 12 --no-pager -o cat | cut -c1-200'
fi
