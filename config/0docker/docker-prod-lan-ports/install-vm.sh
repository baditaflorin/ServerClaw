#!/bin/bash
# Install (or remove) the LAN limit for the DomainScope ports on VM101 docker-prod. Run as root ON THE VM.
#   bash install-vm.sh [--hold SECONDS]   back up, install, apply, verify; an automatic undo fires after SECONDS (default 300)
#                                         unless --confirm is run first. A failed verification undoes at once (exit 5).
#   bash install-vm.sh --confirm          keep it: cancel the pending automatic undo
#   bash install-vm.sh --check            the unit, the pending undo and the live rules (read-only)
#   bash install-vm.sh --undo             remove the rules and the unit now (the conf stays; the backups stay)
# The conf in this directory is installed as /etc/domainscope-lan-allow.conf: the repo is the source of truth, a host edit is backed up
# and replaced. Nothing else on the VM is touched: no other iptables chain, no nftables, no Docker restart.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
SBIN=/usr/local/sbin/domainscope-lan-firewall
CONF=/etc/domainscope-lan-allow.conf
UNIT=/etc/systemd/system/domainscope-lan-firewall.service
STATE=/var/lib/domainscope-lan-firewall
UNDO_UNIT=domainscope-lan-firewall-autoundo
hold=300

undo_now() {
  systemctl disable --now domainscope-lan-firewall.service 2>/dev/null || true
  if [ -x "$SBIN" ]; then "$SBIN" --remove; else bash "$here/domainscope-lan-firewall" --remove; fi
  rm -f "$UNIT" "$SBIN"
  systemctl daemon-reload
}

case "${1:-}" in
  --check)
    systemctl is-active domainscope-lan-firewall.service || true
    systemctl list-timers "$UNDO_UNIT.timer" --no-legend 2>/dev/null || true
    iptables -S DOCKER-USER; iptables -S DOMAINSCOPE-LAN 2>&1 || true
    ip6tables -S INPUT | grep -- '-j DOMAINSCOPE-LAN6' || true; ip6tables -S DOMAINSCOPE-LAN6 2>&1 || true
    exit 0 ;;
  --confirm)
    systemctl stop "$UNDO_UNIT.timer" 2>/dev/null || true
    echo "kept: the automatic undo is cancelled"; exit 0 ;;
  --undo)
    systemctl stop "$UNDO_UNIT.timer" 2>/dev/null || true
    undo_now
    echo "removed (kept $CONF and $STATE)"; exit 0 ;;
  --hold) hold=${2:?--hold needs seconds} ;;
  "") ;;
  *) echo "usage: $0 [--hold SECONDS|--confirm|--check|--undo]" >&2; exit 64 ;;
esac
[[ $hold =~ ^[0-9]+$ ]] && [ "$hold" -ge 60 ] || { echo "--hold must be at least 60 seconds" >&2; exit 64; }
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 64; }

# 1 validate before anything is touched: the conf parses and gives the rules
want=$(DOMAINSCOPE_LAN_CONF="$here/domainscope-lan-allow.conf" bash "$here/domainscope-lan-firewall" --print)
command -v iptables-restore >/dev/null && command -v ip6tables-restore >/dev/null && iptables -S DOCKER-USER >/dev/null \
  || { echo "iptables / ip6tables-restore or the DOCKER-USER chain is missing: nothing changed" >&2; exit 1; }

# 2 back up what this changes
ts=$(date -u +%Y%m%dT%H%M%SZ)
bk="$STATE/$ts"
install -d -m 0700 "$bk"
iptables-save -t filter > "$bk/iptables-filter.v4"
ip6tables-save -t filter > "$bk/ip6tables-filter.v6"
for f in "$SBIN" "$CONF" "$UNIT"; do [ -f "$f" ] && cp -p "$f" "$bk/"; done
echo "backup: $bk"

# 3 arm the automatic undo first: if this shell dies or nobody confirms, the rules go away by themselves
systemctl stop "$UNDO_UNIT.timer" 2>/dev/null || true
systemctl reset-failed "$UNDO_UNIT.service" 2>/dev/null || true
install -m 0755 "$here/domainscope-lan-firewall" "$STATE/undo-firewall"
systemd-run --quiet --unit "$UNDO_UNIT" --on-active="$hold" /bin/sh -c \
  "systemctl disable --now domainscope-lan-firewall.service; $STATE/undo-firewall --remove; rm -f $UNIT $SBIN; systemctl daemon-reload"

# 4 install and apply
install -m 0755 "$here/domainscope-lan-firewall" "$SBIN"
install -m 0644 "$here/domainscope-lan-allow.conf" "$CONF"
install -m 0644 "$here/domainscope-lan-firewall.service" "$UNIT"
systemctl daemon-reload
systemctl enable --quiet domainscope-lan-firewall.service
systemctl restart domainscope-lan-firewall.service

# 5 verify: the live rules are exactly the printed ones, nothing more
live=$( { iptables -S DOMAINSCOPE-LAN | grep '^-A '; iptables -S DOCKER-USER | grep -- '-j DOMAINSCOPE-LAN$';
          ip6tables -S DOMAINSCOPE-LAN6 | grep '^-A '; ip6tables -S INPUT | grep -- '-j DOMAINSCOPE-LAN6$'; } || true)
norm() { sed -E 's#(-s [0-9.]+)( |$)#\1/32\2#' | sort; }
if [ "$(norm <<<"$want")" != "$(norm <<<"$live")" ] || ! systemctl is-active --quiet domainscope-lan-firewall.service; then
  echo "VERIFY FAILED: the live rules differ from the conf; undoing now" >&2
  diff <(norm <<<"$want") <(norm <<<"$live") >&2 || true
  systemctl stop "$UNDO_UNIT.timer" 2>/dev/null || true
  undo_now
  exit 5
fi
echo "applied and verified on this VM; automatic undo in ${hold}s."
echo "check from the edge (200) and from a host that is not allowed (timeout), then: bash $0 --confirm"
