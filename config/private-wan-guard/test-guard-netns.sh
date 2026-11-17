#!/bin/sh
# Run only in an isolated mount and network namespace, e.g. sudo unshare --mount --net ./test-guard-netns.sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$(id -u)" -eq 0 ] || { echo 'run as root inside unshare --mount --net' >&2; exit 1; }
[ "$(readlink /proc/1/ns/net)" != "$(readlink /proc/self/ns/net)" ] || { echo 'refusing to test in host net namespace' >&2; exit 1; }
ip netns add guardpeer
trap 'ip netns delete guardpeer' EXIT
ip link add testwan type veth peer name testpeer
ip link set testpeer netns guardpeer
ip addr add 192.0.2.1/24 dev testwan
ip link set testwan up
ip -n guardpeer link set lo up
ip -n guardpeer addr add 10.200.0.1/32 dev testpeer
ip -n guardpeer addr add 198.51.100.1/32 dev testpeer
ip -n guardpeer link set testpeer up
ip route add 10.200.0.0/16 dev testwan
ip route add 198.51.100.0/24 dev testwan
ip -n guardpeer route add 192.0.2.0/24 dev testpeer
ping -c 1 -W 1 10.200.0.1 >/dev/null
"$here/wan-guard-tc.sh" apply testwan
"$here/wan-guard-tc.sh" apply testwan
"$here/wan-guard-tc.sh" verify testwan
# An earlier filter can intercept traffic before our rules: report unhealthy.
tc filter add dev testwan egress protocol ip pref 10 flower action pass
if "$here/wan-guard-tc.sh" verify testwan >/dev/null 2>&1; then echo 'FAIL bypassing filter was not detected' >&2; exit 1; fi
tc filter del dev testwan egress pref 10
"$here/wan-guard-tc.sh" verify testwan
if ping -c 1 -W 1 10.200.0.1 >/dev/null 2>&1; then echo 'FAIL private packet escaped' >&2; exit 1; fi
ping -c 1 -W 1 198.51.100.1 >/dev/null
nft flush ruleset
if ping -c 1 -W 1 10.200.0.1 >/dev/null 2>&1; then echo 'FAIL private packet escaped after nft flush' >&2; exit 1; fi
"$here/wan-guard-tc.sh" remove testwan
ping -c 1 -W 1 10.200.0.1 >/dev/null
echo 'PASS: baseline, drop, public, nft reload survival and rollback'
