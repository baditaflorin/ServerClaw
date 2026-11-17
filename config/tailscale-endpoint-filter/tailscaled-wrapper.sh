#!/bin/sh
# Start the reviewed endpoint filter only while its upstream package matches.
set -eu
state=/etc/tailscale-endpoint-filter
stock=/usr/sbin/tailscaled
candidate=/opt/tailscale-endpoint-filter/tailscaled-filtered
if [ -r "$state/version" ] && [ -r "$state/sha256" ] && [ -r "$state/interfaces" ] && [ -x "$candidate" ]; then
  expected=$(cat "$state/version")
  actual=$($stock --version | sed -n '1p')
  wanted=$(cat "$state/sha256")
  observed=$(sha256sum "$candidate" | awk '{print $1}')
  interfaces=$(cat "$state/interfaces")
  case "$interfaces" in *[!A-Za-z0-9_,.*?-]*|'') interfaces='' ;; esac
  if [ "$actual" = "$expected" ] && [ "$observed" = "$wanted" ] && [ -n "$interfaces" ]; then
    export TS_AVOID_INTERFACES="$interfaces"
    export TS_DISCO_PRIVATE_ONLINK_ONLY=true
    exec "$candidate" "$@"
  fi
fi
logger -p daemon.err -t tailscale-endpoint-filter 'Patch unavailable or package version changed; using stock daemon and retaining WAN guard'
exec "$stock" "$@"
