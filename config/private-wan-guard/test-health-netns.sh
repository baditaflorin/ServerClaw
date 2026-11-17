#!/bin/sh
# Run only inside sudo unshare --mount --net, on a disposable namespace.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$(id -u)" -eq 0 ] || exit 1
[ "$(readlink /proc/1/ns/net)" != "$(readlink /proc/self/ns/net)" ] || { echo 'refusing host net namespace' >&2; exit 1; }
tmp=$(mktemp -d /var/tmp/wan-health-test.XXXXXX)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/etc" "$tmp/textfile"
cp "$here/wan-guard-tc.sh" "$tmp/bin/wan-guard-tc.sh"
sed "s|/usr/local/sbin|$tmp/bin|g; s|/etc/private-wan-guard|$tmp/etc|g; s|/var/lib/prometheus/node-exporter/textfile|$tmp/textfile|g" "$here/wan-guard-health.sh" > "$tmp/health.sh"
sed 's/WAN_INTERFACE/testwan/g' "$here/rules.nft.example" > "$tmp/etc/rules.nft"
ip link add testwan type dummy
ip link set testwan up
sh "$tmp/health.sh" testwan testwan
"$tmp/bin/wan-guard-tc.sh" verify testwan
# A table with incorrect hooks must be replaced atomically, not merely flushed.
nft delete table inet private_wan_guard
nft add table inet private_wan_guard
nft add chain inet private_wan_guard output '{ type filter hook output priority 10; policy accept; }'
sh "$tmp/health.sh" testwan testwan
# A negated destination match must not be mistaken for a healthy drop rule.
sed 's/ip daddr {/ip daddr != {/' "$tmp/etc/rules.nft" > "$tmp/negated.nft"
nft -f "$tmp/negated.nft"
sh "$tmp/health.sh" testwan testwan
nft flush ruleset
"$tmp/bin/wan-guard-tc.sh" remove testwan
sh "$tmp/health.sh" testwan testwan
"$tmp/bin/wan-guard-tc.sh" verify testwan
grep -qx 'fleet_private_wan_guard_nft_healthy 1' "$tmp/textfile/private_wan_guard.prom"
grep -qx 'fleet_private_wan_guard_tc_healthy 1' "$tmp/textfile/private_wan_guard.prom"
echo 'PASS: restores both guard layers after deletion and reports health'
