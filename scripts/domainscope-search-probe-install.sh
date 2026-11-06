#!/usr/bin/env bash
# Install (or update) the DomainScope search probe job on CT108 from this checkout (docs/runbooks/domainscope-search-probe.md).
#
#   scripts/domainscope-search-probe-install.sh            # install the wrapper and the units, do not enable the timer
#   scripts/domainscope-search-probe-install.sh --enable   # also enable the timer and run the probe once now (read-only: GET requests to search)
#   scripts/domainscope-search-probe-install.sh --status   # the timer, the last run and the metrics
#
# Only files identical to origin/main are installed: reviewed, merged code, never a working tree or an unmerged branch. An installed file
# that is replaced is kept next to it as <file>.bak-<UTC>.
set -euo pipefail

mode="install"
case "${1:-}" in
  "") ;;
  --enable) mode="enable" ;;
  --status) mode="status" ;;
  *) echo "usage: $0 [--enable|--status]" >&2; exit 2 ;;
esac

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bastion="${DSPROBE_BASTION:-0docker_bastion}"
ct() { ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- bash -c $(printf '%q' "$1")"; }
status='systemctl list-timers domainscope-search-probe.timer --no-legend 2>&1 | cut -c1-120
  systemctl show domainscope-search-probe.service -p Result -p ExecMainStatus | tr "\n" " "; echo
  journalctl -u domainscope-search-probe.service -n 15 --no-pager -o cat | cut -c1-200
  grep -v "^#" /var/lib/prometheus-node-exporter/textfile/domainscope_search_probe.prom 2>&1'

if [[ "$mode" == "status" ]]; then
  ct "$status"
  exit 0
fi

files=(scripts/domainscope-search-probe-run config/systemd/domainscope-search-probe.service config/systemd/domainscope-search-probe.timer)
git -C "$repo" fetch --quiet origin main
if ! git -C "$repo" diff --quiet origin/main -- "${files[@]}" || [[ -n "$(git -C "$repo" status --porcelain -- "${files[@]}")" ]]; then
  echo "refusing: these files differ from origin/main (unmerged or uncommitted changes): ${files[*]}" >&2
  echo "merge the change first, update this checkout to origin/main, then install." >&2
  exit 1
fi

remote='set -euo pipefail
d=$(mktemp -d); trap "rm -rf \"$d\"" EXIT; tar -x -C "$d"; cd "$d"
bash -n scripts/domainscope-search-probe-run
for tool in git setpriv timeout flock curl python3; do command -v "$tool" >/dev/null || { echo "missing $tool on the builder" >&2; exit 1; }; done
id nobody >/dev/null
test -d /var/lib/prometheus-node-exporter/textfile || { echo "no node exporter textfile directory" >&2; exit 1; }
ts=$(date -u +%Y%m%dT%H%M%SZ)
for pair in scripts/domainscope-search-probe-run:/usr/local/bin/domainscope-search-probe-run \
  config/systemd/domainscope-search-probe.service:/etc/systemd/system/domainscope-search-probe.service \
  config/systemd/domainscope-search-probe.timer:/etc/systemd/system/domainscope-search-probe.timer; do
  src=${pair%%:*}; dst=${pair#*:}
  if [ -f "$dst" ] && ! cmp -s "$src" "$dst"; then cp -p "$dst" "$dst.bak-$ts"; echo "backup $dst.bak-$ts"; fi
done
install -m 0755 scripts/domainscope-search-probe-run /usr/local/bin/domainscope-search-probe-run
install -m 0644 config/systemd/domainscope-search-probe.service config/systemd/domainscope-search-probe.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/domainscope-search-probe.service /etc/systemd/system/domainscope-search-probe.timer
systemctl daemon-reload
echo "installed /usr/local/bin/domainscope-search-probe-run and the units"'

# No extended attributes: macOS adds some that GNU tar on the builder warns about.
COPYFILE_DISABLE=1 tar --no-xattrs -C "$repo" -cf - "${files[@]}" \
  | ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- bash -c $(printf '%q' "$remote")"

if [[ "$mode" == "enable" ]]; then
  ct 'systemctl enable --now domainscope-search-probe.timer
      systemctl start domainscope-search-probe.service || true'
  ct "$status"
fi
