#!/bin/sh
# Idempotent reconciliation and node_exporter health; never flush another table or qdisc.
set -u
iface=${1:?physical interface required}
wan=${2:?nft WAN interface required}
file=/var/lib/prometheus/node-exporter/textfile/private_wan_guard.prom
nft_ok=0
tc_ok=0
nft_valid() {
  nft -j list table inet private_wan_guard 2>/dev/null | python3 -c '
import json,sys
try: items=json.load(sys.stdin)["nftables"]
except Exception: sys.exit(1)
wanted={"10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","100.64.0.0/10","169.254.0.0/16"}; iface=sys.argv[1]; found=set()
chains={x["chain"]["name"]:x["chain"] for x in items if "chain" in x}
if any(chains.get(n,{}).get("type")!="filter" or chains.get(n,{}).get("hook")!=n or chains.get(n,{}).get("prio")!=-10 for n in ("output","forward")): sys.exit(1)
for item in items:
 r=item.get("rule",{}); expr=r.get("expr",[])
 if r.get("chain") not in ("output","forward") or not any("drop" in e for e in expr): continue
 matches=[e.get("match",{}) for e in expr]; on_iface=any(m.get("op")=="==" and m.get("left",{}).get("meta",{}).get("key")=="oifname" and m.get("right")==iface for m in matches)
 for m in matches:
  if m.get("op") != "==" or m.get("left",{}).get("payload",{}) != {"protocol":"ip","field":"daddr"}: continue
  prefixes=m.get("right",{}).get("set",[]); got={str(x["prefix"]["addr"])+"/"+str(x["prefix"]["len"]) for x in prefixes if "prefix" in x}
  if on_iface and got==wanted: found.add(r["chain"])
if found != {"output","forward"}: sys.exit(1)' "$wan"
}
if ! nft_valid; then
  logger -t private-wan-guard 'nft guard missing or changed; attempting restore'
  # Recreate the owned table in one transaction so a changed hook/priority is repaired too.
  staged=$(mktemp /run/private-wan-reconcile.XXXXXX) || exit 1
  if nft list table inet private_wan_guard >/dev/null 2>&1; then
    printf 'delete table inet private_wan_guard\n' > "$staged"
  fi
  cat /etc/private-wan-guard/rules.nft >> "$staged"
  nft -c -f "$staged" && nft -f "$staged" || true
  rm -f "$staged"
fi
if nft_valid; then nft_ok=1; fi
if ! /usr/local/sbin/wan-guard-tc.sh verify "$iface" >/dev/null 2>&1; then
  logger -t private-wan-guard 'TC guard missing or changed; attempting restore'
  /usr/local/sbin/wan-guard-tc.sh apply "$iface" || true
fi
if /usr/local/sbin/wan-guard-tc.sh verify "$iface" >/dev/null 2>&1; then tc_ok=1; fi
if [ -d "${file%/*}" ]; then
  tmp=$(mktemp "${file}.XXXXXX") || exit 1
  printf 'fleet_private_wan_guard_nft_healthy %s\nfleet_private_wan_guard_tc_healthy %s\nfleet_private_wan_guard_last_check_seconds %s\n' "$nft_ok" "$tc_ok" "$(date +%s)" > "$tmp"
  chmod 644 "$tmp"
  mv -f "$tmp" "$file"
fi
[ "$nft_ok" -eq 1 ] && [ "$tc_ok" -eq 1 ]
