#!/usr/bin/env bash
# new_deployment.sh — Scaffold .local/deployments/<slug>/ for a new deployment.
# Called by `make new-deployment slug=<s> apex=<d>` (ADR 0481).
#
# Creates the directory structure and stub identity/topology/profile/connection
# files. Operator must fill in real values before running converges.
set -euo pipefail

slug="${1:-}"
apex="${2:-}"

if [[ -z "$slug" || -z "$apex" ]]; then
  echo "usage: $0 <slug> <apex-domain>" >&2
  exit 2
fi

# Resolve LOCAL_OVERLAY_ROOT consistently with the Makefile.
repo_root="$(git rev-parse --path-format=absolute --git-common-dir)"
repo_root="${repo_root%/.git}"
overlay_root="${LOCAL_OVERLAY_ROOT:-$repo_root/.local}"

dest="$overlay_root/deployments/$slug"
if [[ -e "$dest" ]]; then
  echo "ERROR: $dest already exists. Choose a different slug or remove the existing dir." >&2
  exit 2
fi

mkdir -p "$dest"/{generated,secrets,receipts,state}

cat > "$dest/identity.yml" <<EOF
# Operator Identity — deployment '$slug'  (ADR 0440 / ADR 0481)
# Fill in every value below to match your deployment.
platform_domain: $apex
platform_operator_email: operator@$apex
platform_operator_name: "$slug Operator"
EOF

cat > "$dest/topology.yml" <<EOF
# Topology for deployment '$slug' — ADR 0440.
# STUB. Replace with your real Proxmox guest layout before bootstrap.
proxmox_guests:
  - name: runtime-control
    vmid: 192
    ipv4: 10.10.10.92
EOF

cat > "$dest/profile.yml" <<EOF
# Service profile for deployment '$slug' — ADR 0441.
profiles:
  - core
extra_services: []
disabled_services: []
service_overrides: {}
EOF

cat > "$dest/connection.yml" <<EOF
schema_version: 1
# Connection registry for deployment '$slug' — ADR 0448.
# STUB. Replace addr/port/user/key with real values.
proxmox_host:
  addr: 0.0.0.0
  port: 22
  user: ops
  key: bootstrap.id_ed25519
guest_ssh:
  user: ops
  key: bootstrap.id_ed25519
  jump_via: proxmox_host
EOF

cat <<EOF
Scaffolded $dest with stub identity/topology/profile/connection files.

Next steps:
  1. Edit $dest/identity.yml — set platform_operator_email / platform_operator_name
  2. Edit $dest/topology.yml — replace stub guest list with your real layout
  3. Edit $dest/connection.yml — set Proxmox host addr/user/key
  4. make use-deployment slug=$slug    # activate this deployment
  5. python scripts/deployment.py validate --slug $slug   # confirm schema OK
  6. make whoami                       # verify the new deployment is active
EOF
