#!/bin/sh
# Test the canonical rendered Proxmox firewall in disposable namespaces.
# Run only with: sudo unshare --mount --net ./config/private-wan-guard/test-hairpin-netns.sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
[ "$(id -u)" -eq 0 ] || exit 1
[ "$(readlink /proc/1/ns/net)" != "$(readlink /proc/self/ns/net)" ] || { echo 'refusing host net namespace' >&2; exit 1; }
tmp=$(mktemp -d /var/tmp/private-edge-hairpin-test.XXXXXX)
serverpid=''
cleanup() { [ -z "$serverpid" ] || kill "$serverpid" 2>/dev/null || true; ip netns del hairpin-client; ip netns del hairpin-edge; rm -rf "$tmp"; }
trap cleanup EXIT
ip netns add hairpin-client
ip netns add hairpin-edge
ip link add brtest type bridge
ip link set brtest up
ip addr add 10.88.0.1/24 dev brtest
ip link add vclient type veth peer name client
ip link add vedge type veth peer name edge
ip link set vclient master brtest
ip link set vedge master brtest
ip link set vclient up
ip link set vedge up
ip link set client netns hairpin-client
ip link set edge netns hairpin-edge
ip -n hairpin-client addr add 10.88.0.2/24 dev client
ip -n hairpin-client link set client up
ip -n hairpin-client link set lo up
ip -n hairpin-client route add default via 10.88.0.1
ip -n hairpin-edge addr add 10.88.0.10/24 dev edge
ip -n hairpin-edge link set edge up
ip -n hairpin-edge link set lo up
ip -n hairpin-edge route add default via 10.88.0.1
ip addr add 203.0.113.1/32 dev lo
ip link set lo up
sysctl -qw net.ipv4.ip_forward=1
ip netns exec hairpin-edge python3 -m http.server 80 --bind 10.88.0.10 >/dev/null 2>&1 &
serverpid=$!
for n in 1 2 3 4 5; do
  if ip netns exec hairpin-client curl -fsS -m 1 http://10.88.0.10/ >/dev/null 2>&1; then break; fi
  sleep 1
done
ip netns exec hairpin-client curl -fsS -m 2 http://10.88.0.10/ >/dev/null
if ip netns exec hairpin-client curl -fsS -m 2 http://203.0.113.1/ >/dev/null 2>&1; then echo 'FAIL expected baseline failure' >&2; exit 1; fi
python3 - "$root" "$tmp/firewall.nft" <<'PY'
import sys
from pathlib import Path
from jinja2 import Environment, StrictUndefined
p=Path(sys.argv[1])/'collections/ansible_collections/lv3/platform/roles/proxmox_network/templates/nftables.conf.j2'
s=Environment(undefined=StrictUndefined).from_string(p.read_text()).render(proxmox_wan_bridge='testwan',proxmox_internal_bridge='brtest',proxmox_internal_network='10.88.0.0/24',proxmox_internal_ipv4='10.88.0.1',proxmox_public_edge_ipv4='10.88.0.10',management_ipv4='203.0.113.1')
Path(sys.argv[2]).write_text(s)
PY
nft -c -f "$tmp/firewall.nft"
nft -f "$tmp/firewall.nft"
ip netns exec hairpin-client curl -fsS -m 3 http://203.0.113.1/ >/dev/null
ip netns exec hairpin-client curl -fsS -m 3 http://10.88.0.10/ >/dev/null
nft flush ruleset
if ip netns exec hairpin-client curl -fsS -m 3 http://203.0.113.1/ >/dev/null 2>&1; then echo 'FAIL rollback did not restore baseline' >&2; exit 1; fi
echo 'PASS: baseline, rendered firewall hairpin, private path and rollback'
