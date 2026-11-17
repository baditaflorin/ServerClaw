#!/bin/sh
# Reconcile endpoint-filter status without reading or printing daemon secrets.
set -u
state=/etc/tailscale-endpoint-filter
candidate=/opt/tailscale-endpoint-filter/tailscaled-filtered
healthy=0
if [ -r "$state/version" ] && [ -r "$state/sha256" ] && [ -r "$state/interfaces" ] && [ -x "$candidate" ]; then
  expected=$(cat "$state/version")
  actual=$(/usr/sbin/tailscaled --version 2>/dev/null | sed -n '1p')
  wanted=$(cat "$state/sha256")
  observed=$(sha256sum "$candidate" 2>/dev/null | awk '{print $1}')
  pid=$(systemctl show tailscaled -p MainPID --value 2>/dev/null)
  exe=$(readlink "/proc/$pid/exe" 2>/dev/null || true)
  interfaces=$(cat "$state/interfaces")
  if [ "$expected" = "$actual" ] && [ "$wanted" = "$observed" ] && [ "$exe" = "$candidate" ] && \
     tr '\000' '\n' < "/proc/$pid/environ" | grep -Fxq "TS_AVOID_INTERFACES=$interfaces" && \
     tr '\000' '\n' < "/proc/$pid/environ" | grep -Fxq "TS_DISCO_PRIVATE_ONLINK_ONLY=true" && \
     systemctl is-active --quiet tailscaled; then
    healthy=1
  fi
fi
node_pid=$(systemctl show prometheus-node-exporter -p MainPID --value 2>/dev/null || true)
dir=$(python3 - "$node_pid" <<'PY'
import pathlib,sys
try:
    args=pathlib.Path('/proc',sys.argv[1],'cmdline').read_bytes().decode().split('\0')
except (OSError,IndexError):
    args=[]
result='/var/lib/prometheus/node-exporter'
for index,arg in enumerate(args):
    if arg.startswith('--collector.textfile.directory='):
        result=arg.split('=',1)[1]
    elif arg=='--collector.textfile.directory' and index+1 < len(args):
        result=args[index+1]
print(result)
PY
)
dir=$(realpath -e "$dir" 2>/dev/null) || { logger -p daemon.err -t tailscale-endpoint-filter 'Node-exporter textfile directory is missing'; exit 1; }
case "$dir" in /var/lib/prometheus/node-exporter|/var/lib/prometheus/node-exporter/*) ;; *)
  logger -p daemon.err -t tailscale-endpoint-filter 'Unsupported node-exporter textfile directory'
  exit 1 ;;
esac
[ -d "$dir" ] || { logger -p daemon.err -t tailscale-endpoint-filter 'Node-exporter textfile path is not a directory'; exit 1; }
tmp=$(mktemp "$dir/.tailscale-endpoint-filter.XXXXXX") || exit 1
printf 'fleet_tailscale_endpoint_filter_healthy %s\nfleet_tailscale_endpoint_filter_sender_guard_active %s\nfleet_tailscale_endpoint_filter_last_check_seconds %s\n' "$healthy" "$healthy" "$(date +%s)" > "$tmp"
chmod 644 "$tmp"
mv -f "$tmp" "$dir/tailscale-endpoint-filter.prom"
if [ "$healthy" -ne 1 ]; then logger -p daemon.err -t tailscale-endpoint-filter 'Endpoint advertisement filter is not active'; exit 1; fi
