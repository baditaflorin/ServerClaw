#!/usr/bin/env bash

set -euo pipefail

# Keep this baseline in sync with the shared host-and-guest package expectations
# until the common package baseline is fully centralized in collection roles.

if [[ -n "${APT_PROXY_URL:-}" ]]; then
  cat > /etc/apt/apt.conf.d/01proxy <<EOF
Acquire::http::Proxy "${APT_PROXY_URL}";
Acquire::https::Proxy "${APT_PROXY_URL}";
EOF
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  acl \
  apt-transport-https \
  auditd \
  ca-certificates \
  chrony \
  curl \
  fail2ban \
  gnupg \
  htop \
  jq \
  needrestart \
  nftables \
  rsyslog \
  sudo \
  tmux \
  unattended-upgrades \
  vim

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

systemctl enable chronyd || systemctl enable chrony || true
systemctl enable rsyslog fail2ban unattended-upgrades auditd

install -d -m 0755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/90-lv3-hardening.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
EOF

if command -v restorecon >/dev/null 2>&1; then
  restorecon -Rv /etc/ssh/sshd_config.d || true
fi

rm -f /etc/apt/apt.conf.d/01proxy
apt-get clean
