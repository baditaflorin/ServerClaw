#!/usr/bin/env bash
# Install (or update) the tailnet policy reconciler on CT108 from this checkout.
#
#   scripts/tailscale-policy-reconcile-install.sh            # install files and units, do not enable the timer
#   scripts/tailscale-policy-reconcile-install.sh --enable   # also enable the timer (REPORT-ONLY: it never applies)
#   scripts/tailscale-policy-reconcile-install.sh --status   # show the timer, the last run and the reconcile state
#
# The reconciler judges every merged policy change with the rules in the installed copy of tailscale_policy_reconcile.py,
# tailscale_policy_sync.py and lockout-guard.json, and refuses to act when those differ from git. So this installer only
# installs files that are IDENTICAL to origin/main: reviewed, merged code, never a working tree or an unmerged branch.
# It never turns applying on: that is the line `FLEET_TS_RECONCILE_ARGS=--apply` in
# /etc/fleet-runner/tailscale-reconcile.env, a deliberate edit (see docs/runbooks/tailscale-metrics-grants.md).
set -euo pipefail

mode="install"
case "${1:-}" in
  "") ;;
  --enable) mode="enable" ;;
  --status) mode="status" ;;
  *) echo "usage: $0 [--enable|--status]" >&2; exit 2 ;;
esac

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bastion="${TS_POLICY_BASTION:-0docker_bastion}"
ct() { ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- bash -c $(printf '%q' "$1")"; }

if [[ "$mode" == "status" ]]; then
  ct 'systemctl list-timers tailscale-policy-reconcile.timer --no-legend 2>&1 | cut -c1-120
      systemctl show tailscale-policy-reconcile.service -p Result -p ExecMainStatus | tr "\n" " "; echo
      python3 /usr/local/lib/tailscale-policy-sync/tailscale_policy_reconcile.py status 2>&1 | tail -25
      echo "mode: $(grep -q -- --apply /etc/fleet-runner/tailscale-reconcile.env 2>/dev/null && echo APPLY || echo report-only)"'
  exit 0
fi

files=(scripts/tailscale_policy_sync.py scripts/tailscale_policy_reconcile.py config/tailscale/lockout-guard.json
       scripts/tailscale-policy-reconcile-run config/systemd/tailscale-policy-reconcile.service
       config/systemd/tailscale-policy-reconcile.timer)

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
python3 -m py_compile scripts/tailscale_policy_sync.py scripts/tailscale_policy_reconcile.py
python3 scripts/tailscale_policy_reconcile.py --help >/dev/null
bash -n scripts/tailscale-policy-reconcile-run
lib=/usr/local/lib/tailscale-policy-sync
install -d -m 0755 "$lib"
install -m 0644 scripts/tailscale_policy_sync.py scripts/tailscale_policy_reconcile.py config/tailscale/lockout-guard.json "$lib/"
install -m 0755 scripts/tailscale-policy-reconcile-run /usr/local/bin/tailscale-policy-reconcile-run
install -m 0644 config/systemd/tailscale-policy-reconcile.service config/systemd/tailscale-policy-reconcile.timer /etc/systemd/system/
install -d -m 0755 /etc/fleet-runner
if [ ! -f /etc/fleet-runner/tailscale-reconcile.env ]; then
  printf "%s\n" "# Operator overrides for tailscale-policy-reconcile-run. Empty ARGS = REPORT ONLY." \
    "export FLEET_TS_RECONCILE_REPO_URL=$REPO_URL" "export FLEET_TS_RECONCILE_ARGS=" > /etc/fleet-runner/tailscale-reconcile.env
  chmod 0644 /etc/fleet-runner/tailscale-reconcile.env
fi
systemctl daemon-reload
echo "installed into $lib (apply mode: $(grep -q -- --apply /etc/fleet-runner/tailscale-reconcile.env && echo ON || echo off))"'

tar --no-xattrs --no-mac-metadata -C "$repo" -cf - "${files[@]}" \
  | ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- env REPO_URL=$(printf '%q' "$url") bash -c $(printf '%q' "$remote")"

if [[ "$mode" == "enable" ]]; then
  ct 'systemctl enable --now tailscale-policy-reconcile.timer
      systemctl start tailscale-policy-reconcile.service || true
      systemctl show tailscale-policy-reconcile.service -p Result -p ExecMainStatus | tr "\n" " "; echo
      journalctl -u tailscale-policy-reconcile.service -n 8 --no-pager -o cat | cut -c1-200'
fi
