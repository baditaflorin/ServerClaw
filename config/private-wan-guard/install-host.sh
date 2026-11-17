#!/bin/sh
# Install a separately owned nft guard, independent physical-egress TC guard,
# and reconciliation timer. Run as root on the target host only.
set -eu
physical=${1:?usage: install-host.sh PHYSICAL_INTERFACE NFT_INTERFACE}
nft_iface=${2:?usage: install-host.sh PHYSICAL_INTERFACE NFT_INTERFACE}
for iface in "$physical" "$nft_iface"; do
  case "$iface" in *[!a-zA-Z0-9_.:-]*|'') echo 'invalid interface' >&2; exit 2;; esac
  ip link show dev "$iface" >/dev/null
done
[ "$(id -u)" -eq 0 ] || { echo 'must be root' >&2; exit 1; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec 9>/run/lock/private-wan-guard-install.lock
flock -n 9 || { echo 'guard install already running' >&2; exit 1; }
stage=$(mktemp -d /run/private-wan-guard.XXXXXX)
trap 'rm -rf "$stage"' EXIT
sed "s/WAN_INTERFACE/$nft_iface/g" "$here/rules.nft.example" > "$stage/rules.nft"
nft -c -f "$stage/rules.nft"
install -d -m 755 /etc/private-wan-guard /usr/local/sbin /var/lib/prometheus/node-exporter/textfile
install -m 644 "$stage/rules.nft" /etc/private-wan-guard/rules.nft
printf 'PHYSICAL_INTERFACE=%s\nNFT_INTERFACE=%s\n' "$physical" "$nft_iface" > "$stage/interfaces.env"
install -m 644 "$stage/interfaces.env" /etc/private-wan-guard/interfaces.env
install -m 755 "$here/wan-guard-tc.sh" /usr/local/sbin/wan-guard-tc.sh
install -m 755 "$here/wan-guard-health.sh" /usr/local/sbin/wan-guard-health.sh
# nftables.service can flush the ruleset at boot. Order the guard afterwards.
sed 's/After=local-fs.target/After=local-fs.target nftables.service/' "$here/private-wan-guard.service" > "$stage/private-wan-guard.service"
install -m 644 "$stage/private-wan-guard.service" /etc/systemd/system/private-wan-guard.service
for unit in 'private-wan-guard-tc@.service' private-wan-guard-health.service private-wan-guard-health.timer; do
  install -m 644 "$here/$unit" "/etc/systemd/system/$unit"
done
systemd-analyze verify /etc/systemd/system/private-wan-guard.service "/etc/systemd/system/private-wan-guard-tc@.service" /etc/systemd/system/private-wan-guard-health.service /etc/systemd/system/private-wan-guard-health.timer
systemctl daemon-reload
# The legacy nft service can already be active, so reconcile it separately below.
systemctl enable --now private-wan-guard.service
systemctl enable --now "private-wan-guard-tc@$physical.service"
systemctl enable --now private-wan-guard-health.timer
/usr/local/sbin/wan-guard-health.sh "$physical" "$nft_iface"
