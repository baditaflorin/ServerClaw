#!/bin/sh
# Restore the vendor unit if the staged canary has not been explicitly accepted.
set -eu
state=/etc/tailscale-endpoint-filter
dropin=/etc/systemd/system/tailscaled.service.d/90-endpoint-filter.conf
[ -f "$state/pending" ] || exit 0
[ -f "$state/dropin.sha256" ] && [ -f "$dropin" ] || { logger -p daemon.err -t tailscale-endpoint-filter 'Canary rollback could not find its owned unit'; exit 1; }
wanted=$(cat "$state/dropin.sha256")
actual=$(sha256sum "$dropin" | awk '{print $1}')
[ "$wanted" = "$actual" ] || { logger -p daemon.err -t tailscale-endpoint-filter 'Canary unit changed; manual rollback required'; exit 1; }
rm "$dropin"
systemctl daemon-reload
systemctl restart tailscaled
systemctl is-active --quiet tailscaled
rm "$state/pending"
logger -t tailscale-endpoint-filter 'Unconfirmed canary rolled back to the vendor daemon'
