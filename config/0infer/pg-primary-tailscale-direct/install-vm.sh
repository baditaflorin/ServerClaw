#!/bin/bash
# Idempotent installer for the VM701 (infer-pg-primary) side: a FIXED tailscaled UDP port (41643) that the hypervisor DNATs to the VM. Run as root on the VM:
#   scp install-vm.sh 0infer_pg_primary:/tmp/ && ssh 0infer_pg_primary 'sudo bash /tmp/install-vm.sh [--undo]'
# Restarting tailscaled briefly drops the tailnet interface (seconds): PostgreSQL itself is not restarted and the streaming replication runs over the
# public path (168.119.211.205), not over the tailnet, so it is unaffected. Only tailnet sessions (the metrics scrape, ssh over the tailnet) blink.
set -euo pipefail
TS=$(date -u +%Y%m%dT%H%M%SZ)
F=/etc/default/tailscaled
want=41643; [ "${1:-}" = "--undo" ] && want=41641
cur=$(sed -n 's/^PORT="\([0-9]*\)".*/\1/p' "$F")
if [ "$cur" = "$want" ]; then echo "PORT already $want"; else
  cp -a "$F" "$F.bak-pg-direct-$TS"
  sed -i "s/^PORT=\"[0-9]*\"/PORT=\"$want\"/" "$F"
  systemctl restart tailscaled
fi
for i in $(seq 1 30); do tailscale status >/dev/null 2>&1 && break; sleep 1; done
ss -uln | grep -q ":$want " || { echo "tailscaled is not listening on UDP $want" >&2; exit 1; }
# Postgres binds the tailnet address: make sure it still answers there
for i in $(seq 1 30); do ip -4 -br a show tailscale0 | grep -q 100.64.0.22 && break; sleep 1; done
echo "tailscaled listens on UDP $want; $(tailscale ip -4)"
