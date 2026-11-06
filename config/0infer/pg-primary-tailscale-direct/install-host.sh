#!/bin/bash
# Idempotent installer for the 0infer HYPERVISOR side of VM701's tailscale direct path. Run as root ON the host (pve01-0infer) from this directory:
#   tar -C config/0infer/pg-primary-tailscale-direct -cf - . | ssh 0infer_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install-host.sh [--undo]; rm -rf $d'
# Order: validate (nft -c), back up what it changes, apply ONLY this table and ONE rule (never the whole ruleset: the other tables hold live NAT state
# of the VMs), verify, undo on failure. The forward rule is added both live (`nft insert`) and to /etc/nftables/infer-proxmox.nft (boot persistence).
set -euo pipefail
cd "$(dirname "$0")"
TS=$(date -u +%Y%m%dT%H%M%SZ)
NFT_FILE=/etc/nftables/infer-pg-primary-tailscale-direct.nft; NFT_TABLE=infer_pg_ts_direct
MAIN=/etc/nftables.conf; FILTER=/etc/nftables/infer-proxmox.nft
MARK="pg-primary tailscale direct path"
RULE='iifname "eno1" oifname "vmbr70" ip daddr 10.70.10.10 udp dport 41643 accept'

live_rule_handle() { nft -a list chain inet infer_filter forward | awk -v m="$RULE" 'index($0, "ip daddr 10.70.10.10 udp dport 41643 accept") {print $NF}'; }

if [ "${1:-}" = "--undo" ]; then
  cp -a "$MAIN" "$MAIN.bak-pg-direct-undo-$TS"; cp -a "$FILTER" "$FILTER.bak-pg-direct-undo-$TS"
  sed -i "\|$NFT_FILE|d" "$MAIN"
  sed -i "/$MARK/d" "$FILTER"
  rm -f "$NFT_FILE"
  nft delete table ip "$NFT_TABLE" 2>/dev/null || true
  for h in $(live_rule_handle); do nft delete rule inet infer_filter forward handle "$h"; done
  echo "undone (backups *.bak-pg-direct-undo-$TS)"; exit 0
fi

# 1) the DNAT/SNAT table
nft -c -f infer-pg-primary-tailscale-direct.nft
install -m 644 infer-pg-primary-tailscale-direct.nft "$NFT_FILE"
if ! grep -qF "include \"$NFT_FILE\"" "$MAIN"; then
  cp -a "$MAIN" "$MAIN.bak-pg-direct-$TS"
  printf 'include "%s"\n' "$NFT_FILE" >> "$MAIN"
fi
nft delete table ip "$NFT_TABLE" 2>/dev/null || true
if ! nft -f "$NFT_FILE"; then
  echo "nft load failed: undoing" >&2
  [ -f "$MAIN.bak-pg-direct-$TS" ] && cp -a "$MAIN.bak-pg-direct-$TS" "$MAIN"
  rm -f "$NFT_FILE"; exit 1
fi

# 2) the one forward-accept rule: persisted in infer-proxmox.nft (boot) and inserted live (idempotent)
if ! grep -qF "$MARK" "$FILTER"; then
  cp -a "$FILTER" "$FILTER.bak-pg-direct-$TS"
  # right after the existing infer-runtime direct-path rule if present, else at the top of the forward chain
  if grep -q 'udp dport 41642 accept' "$FILTER"; then
    sed -i "/udp dport 41642 accept/a\\        $RULE  # $MARK (2026-10-17)" "$FILTER"
  else
    sed -i "/type filter hook forward priority filter; policy drop;/a\\        $RULE  # $MARK (2026-10-17)" "$FILTER"
  fi
fi
if [ -z "$(live_rule_handle)" ]; then
  nft insert rule inet infer_filter forward $RULE comment \"$MARK\"
fi

# 3) verify
nft list table ip "$NFT_TABLE" | grep -q "dnat to 10.70.10.10:41643" || { echo "DNAT missing after load" >&2; exit 1; }
[ -n "$(live_rule_handle)" ] || { echo "forward rule missing after insert" >&2; exit 1; }
nft -c -f "$MAIN" >/dev/null || { echo "WARNING: $MAIN no longer validates as a whole; backups *.bak-pg-direct-$TS" >&2; exit 1; }
echo "nft: $NFT_TABLE loaded and persisted, forward rule live and in $FILTER (backups *.bak-pg-direct-$TS)"
