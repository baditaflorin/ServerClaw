#!/usr/bin/env bash

set -euo pipefail

if [[ -n "${APT_PROXY_URL:-}" ]]; then
  cat > /etc/apt/apt.conf.d/01proxy <<EOF
Acquire::http::Proxy "${APT_PROXY_URL}";
Acquire::https::Proxy "${APT_PROXY_URL}";
EOF
fi

export DEBIAN_FRONTEND=noninteractive

install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker containerd

# Create cert directory for private registry (domain set by platform_domain in identity.yml)
# Override REGISTRY_DOMAIN at build time or leave as placeholder
install -d -m 0755 /etc/docker/certs.d/${REGISTRY_DOMAIN:-registry.example.com}
cat > /etc/docker/daemon.json <<'EOF'
{
  "features": {
    "buildkit": true
  },
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  }
}
EOF

rm -f /etc/apt/apt.conf.d/01proxy
apt-get clean
