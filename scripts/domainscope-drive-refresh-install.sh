#!/usr/bin/env bash
# Install (or update) the DomainScope Drive data room refresh job on CT108 from this checkout (docs/runbooks/domainscope-drive-refresh.md).
#
#   scripts/domainscope-drive-refresh-install.sh            # install the wrapper and the units, do not enable the timer
#   scripts/domainscope-drive-refresh-install.sh --enable   # also enable the timer and run the refresh once now as a DRY RUN (it prints what it would change, writes nothing)
#   scripts/domainscope-drive-refresh-install.sh --status   # the timer, the last run and the metrics
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
bastion="${DSDRIVE_BASTION:-0docker_bastion}"
ct() { ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- bash -c $(printf '%q' "$1")"; }
status='systemctl list-timers domainscope-drive-refresh.timer --no-legend 2>&1 | cut -c1-120
  systemctl show domainscope-drive-refresh.service -p Result -p ExecMainStatus | tr "\n" " "; echo
  journalctl -u domainscope-drive-refresh.service -n 15 --no-pager -o cat | cut -c1-200
  grep -v "^#" /var/lib/prometheus-node-exporter/textfile/domainscope_drive_refresh.prom 2>&1'

if [[ "$mode" == "status" ]]; then
  ct "$status"
  exit 0
fi

files=(scripts/domainscope-drive-refresh-run scripts/domainscope-drive-figures.py config/systemd/domainscope-drive-refresh.service config/systemd/domainscope-drive-refresh.timer)
git -C "$repo" fetch --quiet origin main
if ! git -C "$repo" diff --quiet origin/main -- "${files[@]}" || [[ -n "$(git -C "$repo" status --porcelain -- "${files[@]}")" ]]; then
  echo "refusing: these files differ from origin/main (unmerged or uncommitted changes): ${files[*]}" >&2
  echo "merge the change first, update this checkout to origin/main, then install." >&2
  exit 1
fi

remote='set -euo pipefail
d=$(mktemp -d); trap "rm -rf \"$d\"" EXIT; tar -x -C "$d"; cd "$d"
bash -n scripts/domainscope-drive-refresh-run
for tool in git timeout flock bash python3 ssh; do command -v "$tool" >/dev/null || { echo "missing $tool on the builder" >&2; exit 1; }; done
# go is in /usr/local/go/bin, which is on a login shell PATH only; the wrapper looks there too.
{ command -v go >/dev/null || test -x /usr/local/go/bin/go; } || { echo "missing go on the builder" >&2; exit 1; }
test -f /root/bin/fv.sh || { echo "no vault helper /root/bin/fv.sh on the builder" >&2; exit 1; }
test -d /var/lib/prometheus-node-exporter/textfile || { echo "no node exporter textfile directory" >&2; exit 1; }
ts=$(date -u +%Y%m%dT%H%M%SZ)
for pair in scripts/domainscope-drive-refresh-run:/usr/local/bin/domainscope-drive-refresh-run \
  scripts/domainscope-drive-figures.py:/usr/local/lib/domainscope-drive-refresh/figures.py \
  config/systemd/domainscope-drive-refresh.service:/etc/systemd/system/domainscope-drive-refresh.service \
  config/systemd/domainscope-drive-refresh.timer:/etc/systemd/system/domainscope-drive-refresh.timer; do
  src=${pair%%:*}; dst=${pair#*:}
  if [ -f "$dst" ] && ! cmp -s "$src" "$dst"; then cp -p "$dst" "$dst.bak-$ts"; echo "backup $dst.bak-$ts"; fi
done
install -m 0755 scripts/domainscope-drive-refresh-run /usr/local/bin/domainscope-drive-refresh-run
install -d -m 0755 /usr/local/lib/domainscope-drive-refresh
install -m 0644 scripts/domainscope-drive-figures.py /usr/local/lib/domainscope-drive-refresh/figures.py
install -m 0644 config/systemd/domainscope-drive-refresh.service config/systemd/domainscope-drive-refresh.timer /etc/systemd/system/
systemd-analyze verify /etc/systemd/system/domainscope-drive-refresh.service /etc/systemd/system/domainscope-drive-refresh.timer
systemctl daemon-reload
echo "installed /usr/local/bin/domainscope-drive-refresh-run and the units"'

# No extended attributes: macOS adds some that GNU tar on the builder warns about.
COPYFILE_DISABLE=1 tar --no-xattrs -C "$repo" -cf - "${files[@]}" \
  | ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" "pct exec 108 -- bash -c $(printf '%q' "$remote")"

if [[ "$mode" == "enable" ]]; then
  ct 'systemctl enable --now domainscope-drive-refresh.timer
      systemd-run --quiet --wait --collect --pipe --property=Type=oneshot --property=TimeoutStartSec=25min \
        --property=User=root --setenv=HOME=/root \
        --property=EnvironmentFile=-/etc/default/domainscope-drive-refresh \
        /usr/bin/flock -n /run/lock/domainscope-drive-refresh.lock /usr/local/bin/domainscope-drive-refresh-run --dry-run'
  ct "$status"
fi
