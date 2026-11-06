#!/bin/bash
# Idempotent installer for the infer runtime VM (infer-runtime, 10.70.10.30): put the machine's own FQDN in /etc/hosts. Run as root on the VM:
#   scp install-vm.sh 0infer_runtime:/tmp/ && ssh 0infer_runtime 'sudo bash /tmp/install-vm.sh [--undo]'
# Without the entry every lookup of the host's own name falls through to nss-myhostname, which walks all ~460 network interfaces (364 veth) and took
# 16-22 s of kernel time per call: `sudo` resolves the local hostname on every invocation, so every `sudo -n true` took 10-20 s and a pool deploy spent
# minutes in sudo alone. With the entry, `files` answers first and the same call takes 0.01 s. See README.md. Nothing is restarted.
set -euo pipefail
FQDN=$(hostname)
SHORT=${FQDN%%.*}
F=/etc/hosts
LINE=$(printf '127.0.1.1\t%s %s' "$FQDN" "$SHORT")
[ "$FQDN" != "$SHORT" ] || LINE=$(printf '127.0.1.1\t%s' "$FQDN")
if [ "${1:-}" = "--undo" ]; then
  if grep -qxF "$LINE" "$F"; then
    cp -a "$F" "$F.bak-ownname-undo-$(date -u +%Y%m%dT%H%M%SZ)"
    grep -vxF "$LINE" "$F" > "$F.new" && cat "$F.new" > "$F" && rm -f "$F.new"
    echo "removed: $LINE"
  else echo "entry not present"; fi
  exit 0
fi
if awk -v n="$FQDN" '!/^[[:space:]]*#/ { for (i = 2; i <= NF; i++) if ($i == n) found = 1 } END { exit !found }' "$F"; then
  echo "$FQDN already has an /etc/hosts entry"
else
  cp -a "$F" "$F.bak-ownname-$(date -u +%Y%m%dT%H%M%SZ)"
  printf '%s\n' "$LINE" >> "$F"
  echo "added: $LINE"
fi
TIMEFORMAT='lookup of the own name: %R s'
time python3 -c 'import socket; socket.getaddrinfo(socket.gethostname(), None)'
