#!/bin/sh
# Defense in depth against private IPv4 frames leaving a public physical uplink.
# Owns clsact egress preference 49000 handles 1-5 only; never deletes a qdisc.
set -eu
operation=${1:?usage: wan-guard-tc.sh apply\|verify\|remove INTERFACE}
iface=${2:?missing physical uplink interface}
case "$iface" in *[!a-zA-Z0-9_.:-]*|'') echo 'invalid interface' >&2; exit 2;; esac
ip link show dev "$iface" >/dev/null
prefixes='10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16'
check_owned() {
  tc -j filter show dev "$iface" egress | python3 -c '
import json,sys
rules=json.load(sys.stdin)
wanted={1:"10.0.0.0/8",2:"172.16.0.0/12",3:"192.168.0.0/16",4:"100.64.0.0/10",5:"169.254.0.0/16"}
for r in rules:
 if r.get("pref") != 49000: continue
 o=r.get("options",{})
 if not o: continue
 if r.get("kind") != "flower" or wanted.get(o.get("handle")) != o.get("keys",{}).get("dst_ip"):
  sys.exit("TC preference 49000 is already owned by another filter")'
}
case "$operation" in
  apply)
    if ! tc qdisc show dev "$iface" | grep -q '^qdisc clsact '; then
      tc qdisc add dev "$iface" clsact
    fi
    check_owned
    i=0
    for prefix in $prefixes; do
      i=$((i + 1))
      tc filter replace dev "$iface" egress protocol ip pref 49000 handle "$i" flower skip_hw dst_ip "$prefix" action drop
    done
    ;;
  verify)
    filters=$(tc -j -s filter show dev "$iface" egress)
    printf '%s\n' "$filters" | python3 -c '
import json,sys
rules=json.load(sys.stdin)
if any(r.get("chain",0)==0 and isinstance(r.get("pref"),int) and r["pref"]<49000 for r in rules):
 sys.exit("higher-priority TC filters could bypass the private WAN guard")
wanted={"10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","100.64.0.0/10","169.254.0.0/16"}
found=set()
for rule in rules:
 if rule.get("pref") != 49000 or rule.get("kind") != "flower" or rule.get("protocol") != "ip": continue
 opts=rule.get("options",{}); keys=opts.get("keys",{}); acts=opts.get("actions",[])
 if opts.get("skip_hw") and any(a.get("kind")=="gact" and a.get("control_action",{}).get("type")=="drop" for a in acts): found.add(keys.get("dst_ip"))
if found != wanted: sys.exit("private WAN TC rules missing: " + repr(sorted(wanted-found)))
print("private WAN TC guard verified")'
    ;;
  remove)
    check_owned
    i=0
    for prefix in $prefixes; do
      i=$((i + 1))
      tc filter del dev "$iface" egress protocol ip pref 49000 handle "$i" flower 2>/dev/null || true
    done
    ;;
  *) echo 'unknown operation' >&2; exit 2;;
esac
