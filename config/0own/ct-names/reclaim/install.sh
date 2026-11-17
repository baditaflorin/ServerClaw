#!/usr/bin/env bash
# Install one host's timer, but do not enable it until alerting is verified.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
usage() { echo "usage: $0 guest|hypervisor [--install|--enable]" >&2; exit 2; }
[ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage
case "$1" in
  guest) unit=ct-names-reclaim; script=ct-names-reclaim.py ;;
  hypervisor) unit=ct-names-zvol-metrics; script=ct-names-zvol-metrics.py ;;
  *) usage ;;
esac
action="${2:---plan}"
case "$action" in --plan|--install|--enable) ;; *) usage ;; esac
if [ "$action" = --plan ]; then
  echo "Would install ${unit} and ${script}; --install leaves the timer disabled."
  echo "Enable only after the alert rules and telemetry path have been verified."
  exit 0
fi
[ "$(id -u)" = 0 ] || { echo 'root required' >&2; exit 1; }
if [ "$action" = --enable ]; then
  test -x "/usr/local/libexec/${script}"
  systemctl enable --now "${unit}.timer"
  systemctl is-active --quiet "${unit}.timer"
  exit 0
fi
if systemctl is-active --quiet "${unit}.timer" || systemctl is-active --quiet "${unit}.service"; then
  echo "Refusing to replace active ${unit}; stop the timer and wait for its service first." >&2
  exit 1
fi
backup="/root/ct-names-backups/reclaim-install-$(date -u +%Y%m%dT%H%M%S%N)"
mkdir -p "$backup" /usr/local/libexec /etc/systemd/system /var/lib/prometheus/node-exporter/textfile
files=("/usr/local/libexec/${script}" "/etc/systemd/system/${unit}.service" "/etc/systemd/system/${unit}.timer")
for f in "${files[@]}"; do
  if [ -e "$f" ]; then cp -a "$f" "$backup/$(basename "$f")"; else touch "$backup/$(basename "$f").absent"; fi
done
rollback() {
  for f in "${files[@]}"; do
    if [ -e "$backup/$(basename "$f").absent" ]; then rm -f "$f"; else cp -a "$backup/$(basename "$f")" "$f"; fi
  done
  systemctl daemon-reload || true
}
trap rollback ERR
install -m 0755 "$here/$script" "${files[0]}"
install -m 0644 "$here/${unit}.service" "${files[1]}"
install -m 0644 "$here/${unit}.timer" "${files[2]}"
systemd-analyze verify "${files[1]}" "${files[2]}"
systemctl daemon-reload
trap - ERR
echo "Installed ${unit}, not enabled; rollback files: ${backup}"
