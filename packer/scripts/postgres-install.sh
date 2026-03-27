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
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg
chmod a+r /etc/apt/keyrings/postgresql.gpg

. /etc/os-release
cat > /etc/apt/sources.list.d/pgdg.list <<EOF
deb [signed-by=/etc/apt/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main
EOF

apt-get update
apt-get install -y postgresql-16 postgresql-client-16 postgresql-contrib-16 barman-cli

install -d -m 0755 /etc/postgresql-common/createcluster.d
cat > /etc/postgresql-common/createcluster.d/lv3.conf <<'EOF'
create_main_cluster = true
start_conf = auto
data_directory = /var/lib/postgresql/%v/%c
EOF

cat > /etc/postgresql/16/main/conf.d/lv3-template.conf <<'EOF'
shared_preload_libraries = 'pg_stat_statements'
password_encryption = scram-sha-256
EOF

systemctl enable postgresql

rm -f /etc/apt/apt.conf.d/01proxy
apt-get clean
