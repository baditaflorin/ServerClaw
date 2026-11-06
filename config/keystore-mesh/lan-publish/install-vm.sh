#!/bin/bash
# Install (or remove) the LAN firewall for the keystore API on a mesh node VM.
#   sudo bash install-vm.sh            install + apply (idempotent, keeps an existing /etc/keystore-lan-allow.conf)
#   sudo bash install-vm.sh --check    print the rules that are live
#   sudo bash install-vm.sh --undo     remove the rules, the unit and the files (the compose line is yours to revert)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
LAN_IP=${KEYSTORE_LAN_IP:-10.10.10.91}; PORT=${KEYSTORE_LAN_PORT:-18021}; IFACE=${KEYSTORE_LAN_IF:-eth0}
jump=(-i "$IFACE" -p tcp -m conntrack --ctorigdst "$LAN_IP" --ctorigdstport "$PORT" --ctdir ORIGINAL -j KEYSTORE-LAN)
case "${1:-}" in
  --check)
    systemctl is-active keystore-lan-firewall.service || true
    iptables -S DOCKER-USER; iptables -S KEYSTORE-LAN 2>&1 || true
    exit 0 ;;
  --undo)
    systemctl disable --now keystore-lan-firewall.service 2>/dev/null || true
    while iptables -C DOCKER-USER "${jump[@]}" 2>/dev/null; do iptables -D DOCKER-USER "${jump[@]}"; done
    iptables -F KEYSTORE-LAN 2>/dev/null || true; iptables -X KEYSTORE-LAN 2>/dev/null || true
    rm -f /etc/systemd/system/keystore-lan-firewall.service /usr/local/sbin/keystore-lan-firewall
    systemctl daemon-reload
    echo "removed (kept /etc/keystore-lan-allow.conf)"; exit 0 ;;
  "") ;;
  *) echo "usage: $0 [--check|--undo]" >&2; exit 64 ;;
esac
ts=$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0755 /usr/local/sbin
[ -f /usr/local/sbin/keystore-lan-firewall ] && cp -p /usr/local/sbin/keystore-lan-firewall "/usr/local/sbin/keystore-lan-firewall.bak-$ts"
install -m 0755 "$here/keystore-lan-firewall" /usr/local/sbin/keystore-lan-firewall
[ -f /etc/keystore-lan-allow.conf ] || install -m 0644 "$here/keystore-lan-allow.conf" /etc/keystore-lan-allow.conf
install -m 0644 "$here/keystore-lan-firewall.service" /etc/systemd/system/keystore-lan-firewall.service
/usr/local/sbin/keystore-lan-firewall --print >/dev/null     # validate the allow list before anything is applied
systemctl daemon-reload
systemctl enable keystore-lan-firewall.service
systemctl restart keystore-lan-firewall.service
systemctl is-active keystore-lan-firewall.service
iptables -S KEYSTORE-LAN
