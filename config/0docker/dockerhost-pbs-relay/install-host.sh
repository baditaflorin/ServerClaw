#!/bin/bash
# Idempotent installer for the VM100 -> own-pbs relay on the 0docker hypervisor. Run as root ON the host:
#   tar -C config/0docker/dockerhost-pbs-relay -cf - . | ssh 0docker_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install-host.sh [--undo]; rm -rf $d'
# Validates first (nft -c), loads ONLY this table (never `flush ruleset`), persists it as its own systemd unit (this host's /etc/nftables.conf is a stock file and nftables.service
# is disabled; fleet-lockdown works the same way), keeps a copy of whatever it replaces, and undoes itself when the loaded table does not contain the rule.
set -euo pipefail
cd "$(dirname "$0")"
TS=$(date -u +%Y%m%dT%H%M%SZ)
NFT_FILE=/etc/nftables/dockerhost-pbs-relay.nft; UNIT=/etc/systemd/system/dockerhost-pbs-relay.service; TABLE=dockerhost_pbs_relay
if [ "${1:-}" = "--undo" ]; then
  systemctl disable --now dockerhost-pbs-relay.service 2>/dev/null || true
  nft delete table ip "$TABLE" 2>/dev/null || true
  rm -f "$NFT_FILE" "$UNIT"; systemctl daemon-reload
  echo "undone: unit and $NFT_FILE removed, table $TABLE deleted"; exit 0
fi
nft -c -f dockerhost-pbs-relay.nft
install -d -m 755 /etc/nftables
for f in "$NFT_FILE" "$UNIT"; do [ -f "$f" ] && cp -a "$f" "$f.bak-$TS" || true; done
install -m 644 dockerhost-pbs-relay.nft "$NFT_FILE"
install -m 644 dockerhost-pbs-relay.service "$UNIT"
systemctl daemon-reload
systemctl enable dockerhost-pbs-relay.service >/dev/null 2>&1
if ! systemctl restart dockerhost-pbs-relay.service; then
  echo "unit failed to load the table: undoing" >&2
  bash "$0" --undo; exit 1
fi
if ! nft list table ip "$TABLE" | grep -q "dnat to 100.64.0.11:8007"; then
  echo "rule not present after load: undoing" >&2
  bash "$0" --undo; exit 1
fi
echo "relay up: $(systemctl is-active dockerhost-pbs-relay.service), enabled: $(systemctl is-enabled dockerhost-pbs-relay.service)"
nft list table ip "$TABLE" | grep -E "dnat|masquerade|maxseg" | sed -E 's/^\s+//'
