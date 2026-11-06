#!/bin/bash
# PROMOTE the standby: start keystore then vault from the latest synced copy. Run on infer-tier0 as root.
# Prints freshness first. It does NOT change DNS/gateway upstreams (that is a separate, deliberate step in the runbook).
set -euo pipefail
cd /opt/tier0/vault-standby
for d in vault keystore; do f=data/$d/.last_sync; [ -f $f ] && echo "$d copy age: $(( $(date +%s) - $(cat $f) ))s" || { echo "$d: NO synced copy"; exit 1; }; done
docker-compose up -d keystore; sleep 5; docker-compose up -d vault; sleep 5
curl -fsS -m 5 http://127.0.0.1:18140/health && echo && echo "vault standby serving on 127.0.0.1:18140 (promoted)"
