#!/bin/sh
# Restore the verified previous filtered daemon after an unconfirmed upgrade.
set -eu
# Serialize a timer-triggered rollback with confirmation. Callers that already
# own the installer lock pass the internal marker and retain their inherited fd.
if [ "${TS_FILTER_LOCK_HELD:-0}" != 1 ]; then
  exec 9>/run/lock/tailscale-endpoint-filter.lock
  flock -w 60 9 || { logger -p daemon.err -t tailscale-endpoint-filter 'Upgrade rollback could not acquire the installer lock'; exit 1; }
fi
state=/etc/tailscale-endpoint-filter
pending="$state/pending-upgrade"
[ -f "$pending" ] || exit 0
previous=$(cat "$pending")
case "$previous" in *[!0-9a-f]*|'') echo 'invalid previous checksum' >&2; exit 1;; esac
[ "${#previous}" -eq 64 ] || { echo 'invalid previous checksum length' >&2; exit 1; }
backup="/var/lib/tailscale-endpoint-filter/backups/$previous"
[ -f "$backup/tailscaled-filtered" ] && [ "$(sha256sum "$backup/tailscaled-filtered" | awk '{print $1}')" = "$previous" ] || { echo 'previous binary backup is invalid' >&2; exit 1; }
for name in tailscaled-wrapper.sh health.sh; do
  [ -f "$backup/$name" ] && [ -f "$backup/$name.sha256" ] && [ "$(sha256sum "$backup/$name" | awk '{print $1}')" = "$(cat "$backup/$name.sha256")" ] || { echo 'previous script backup is invalid' >&2; exit 1; }
done
newbin="/opt/tailscale-endpoint-filter/.rollback-bin.$$"
newwrapper="/usr/local/libexec/.rollback-wrapper.$$"
newhealth="/usr/local/libexec/.rollback-health.$$"
newsha="$state/.rollback-sha.$$"
trap 'rm -f "$newbin" "$newwrapper" "$newhealth" "$newsha"' EXIT
install -m 755 "$backup/tailscaled-filtered" "$newbin"
install -m 755 "$backup/tailscaled-wrapper.sh" "$newwrapper"
install -m 755 "$backup/health.sh" "$newhealth"
printf '%s\n' "$previous" > "$newsha"
mv -f "$newbin" /opt/tailscale-endpoint-filter/tailscaled-filtered
mv -f "$newwrapper" /usr/local/libexec/tailscaled-endpoint-filter-wrapper
mv -f "$newhealth" /usr/local/libexec/tailscale-endpoint-filter-health
mv -f "$newsha" "$state/sha256"
systemctl restart tailscaled
systemctl is-active --quiet tailscaled
pid=$(systemctl show tailscaled -p MainPID --value)
[ "$(readlink "/proc/$pid/exe")" = /opt/tailscale-endpoint-filter/tailscaled-filtered ] || { echo 'previous filtered daemon was not restored' >&2; exit 1; }
/usr/local/libexec/tailscale-endpoint-filter-health
rm -f "$state/pending" "$pending"
logger -t tailscale-endpoint-filter 'Unconfirmed upgrade restored the previous filtered daemon'
