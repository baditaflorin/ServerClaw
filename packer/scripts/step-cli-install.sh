#!/usr/bin/env bash

set -euo pipefail

STEP_VERSION="${STEP_VERSION:-0.30.1}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

arch="$(dpkg --print-architecture)"
case "$arch" in
  amd64)
    step_arch="amd64"
    ;;
  arm64)
    step_arch="arm64"
    ;;
  *)
    echo "Unsupported architecture: $arch" >&2
    exit 1
    ;;
esac

curl -fsSL -o "$tmpdir/step-cli.tgz" \
  "https://github.com/smallstep/cli/releases/download/v${STEP_VERSION}/step_linux_${STEP_VERSION}_${step_arch}.tar.gz"
tar -xzf "$tmpdir/step-cli.tgz" -C "$tmpdir"
install -m 0755 "$tmpdir/step_${STEP_VERSION}/bin/step" /usr/local/bin/step

install -d -m 0755 /etc/profile.d
cat > /etc/profile.d/lv3-step.sh <<'EOF'
export STEPPATH="${STEPPATH:-$HOME/.step}"
EOF
