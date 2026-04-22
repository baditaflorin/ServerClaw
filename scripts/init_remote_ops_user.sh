#!/usr/bin/env bash
# Idempotent creation of the `ops` sudoer on a fresh remote host.
#
# Background: on provider images whose default user is `root` (Hetzner
# installimage, stock Debian cloud images, etc.), `make bootstrap` cannot
# SSH as `ops` until that account exists. This script is the one-shot
# prerequisite that turns a root-only box into one the rest of bootstrap
# can drive. Diary-flagged gap — see docs/diaries/2026-04-22-fork-bootstrap.md
# and the follow-up note in ADR 0437.
#
# Inputs (env or flags):
#   REMOTE_HOST        target IPv4/IPv6 or DNS name         (required)
#   REMOTE_ROOT_USER   SSH user with initial root access    (default: root)
#   REMOTE_ROOT_KEY    private key for the root account     (required)
#   OPS_USER           account to create                    (default: ops)
#   OPS_PUBKEY_PATH    public key to install for ops        (required)
#   OPS_PROBE_KEY      private key to probe ops with        (optional; if set and
#                                                            probe succeeds, script
#                                                            exits cleanly without
#                                                            touching the box)
#   SSH_KNOWN_HOSTS    path to pinned known_hosts file      (optional)
#
# Exit codes:
#   0  ops is reachable (either already, or after provisioning)
#   1  usage / missing inputs
#   2  provisioning ran but post-verify still cannot reach ops

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_ROOT_USER="${REMOTE_ROOT_USER:-root}"
REMOTE_ROOT_KEY="${REMOTE_ROOT_KEY:-}"
OPS_USER="${OPS_USER:-ops}"
OPS_PUBKEY_PATH="${OPS_PUBKEY_PATH:-}"
OPS_PROBE_KEY="${OPS_PROBE_KEY:-}"
SSH_KNOWN_HOSTS="${SSH_KNOWN_HOSTS:-}"

usage() {
  sed -n '2,30p' "$0" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host) REMOTE_HOST="$2"; shift 2 ;;
    --root-user) REMOTE_ROOT_USER="$2"; shift 2 ;;
    --root-key) REMOTE_ROOT_KEY="$2"; shift 2 ;;
    --ops-user) OPS_USER="$2"; shift 2 ;;
    --ops-pubkey) OPS_PUBKEY_PATH="$2"; shift 2 ;;
    --ops-probe-key) OPS_PROBE_KEY="$2"; shift 2 ;;
    --known-hosts) SSH_KNOWN_HOSTS="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "unknown flag: $1" >&2; usage ;;
  esac
done

if [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_ROOT_KEY" ] || [ -z "$OPS_PUBKEY_PATH" ]; then
  echo "error: REMOTE_HOST, REMOTE_ROOT_KEY, OPS_PUBKEY_PATH are required" >&2
  usage
fi

if [ ! -f "$REMOTE_ROOT_KEY" ]; then
  echo "error: root key not found: $REMOTE_ROOT_KEY" >&2
  exit 1
fi
if [ ! -f "$OPS_PUBKEY_PATH" ]; then
  echo "error: ops pubkey not found: $OPS_PUBKEY_PATH" >&2
  exit 1
fi

OPS_PUBKEY_CONTENT="$(tr -d '\r\n' < "$OPS_PUBKEY_PATH")"
if [ -z "$OPS_PUBKEY_CONTENT" ]; then
  echo "error: ops pubkey file is empty: $OPS_PUBKEY_PATH" >&2
  exit 1
fi

ssh_common=(
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=15
)
if [ -n "$SSH_KNOWN_HOSTS" ] && [ -f "$SSH_KNOWN_HOSTS" ]; then
  ssh_common+=(-o "UserKnownHostsFile=$SSH_KNOWN_HOSTS" -o StrictHostKeyChecking=yes)
else
  ssh_common+=(-o StrictHostKeyChecking=accept-new)
fi

probe_ops() {
  local key="$1"
  ssh "${ssh_common[@]}" -i "$key" "$OPS_USER@$REMOTE_HOST" \
    "sudo -n true && id -un" 2>/dev/null
}

# Fast path: if ops is already a working sudoer, do nothing.
if [ -n "$OPS_PROBE_KEY" ] && [ -f "$OPS_PROBE_KEY" ]; then
  if probe_ops "$OPS_PROBE_KEY" >/dev/null; then
    echo "ok: $OPS_USER@$REMOTE_HOST already reachable with passwordless sudo — nothing to do"
    exit 0
  fi
fi

echo "--> provisioning $OPS_USER on $REMOTE_HOST via $REMOTE_ROOT_USER (root key: $REMOTE_ROOT_KEY)"

# Remote script is streamed over stdin so it needs no temp file on either side.
# All commands are idempotent (useradd -f 0, grep-before-append, install -m).
remote_script=$(cat <<'EOS'
set -euo pipefail
OPS_USER="__OPS_USER__"
OPS_PUBKEY='__OPS_PUBKEY__'

# Create account if missing, with sudo group and bash shell.
if ! id -u "$OPS_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash --user-group "$OPS_USER"
fi

# Ensure sudo group membership (works whether useradd above created the user
# or it already existed with a different group setup).
if getent group sudo >/dev/null; then
  usermod -aG sudo "$OPS_USER"
fi

# Install ssh key for ops.
home="$(getent passwd "$OPS_USER" | cut -d: -f6)"
install -d -m 0700 -o "$OPS_USER" -g "$OPS_USER" "$home/.ssh"
auth="$home/.ssh/authorized_keys"
touch "$auth"
chmod 0600 "$auth"
chown "$OPS_USER:$OPS_USER" "$auth"
if ! grep -qxF "$OPS_PUBKEY" "$auth"; then
  printf '%s\n' "$OPS_PUBKEY" >> "$auth"
fi

# Passwordless sudo for ops, validated before install (fail-closed).
sudoers_tmp="$(mktemp)"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$OPS_USER" > "$sudoers_tmp"
chmod 0440 "$sudoers_tmp"
if visudo -cf "$sudoers_tmp" >/dev/null; then
  install -m 0440 "$sudoers_tmp" "/etc/sudoers.d/90-${OPS_USER}-nopasswd"
  rm -f "$sudoers_tmp"
else
  rm -f "$sudoers_tmp"
  echo "visudo rejected the sudoers fragment for $OPS_USER" >&2
  exit 1
fi

# Echo a small receipt for the caller.
echo "ops-user=$OPS_USER home=$home groups=$(id -Gn "$OPS_USER")"
EOS
)

# Fill in the placeholders. Using a printf chain avoids shell-escaping surprises.
remote_script="${remote_script//__OPS_USER__/$OPS_USER}"
remote_script="${remote_script//__OPS_PUBKEY__/$OPS_PUBKEY_CONTENT}"

ssh "${ssh_common[@]}" -i "$REMOTE_ROOT_KEY" "$REMOTE_ROOT_USER@$REMOTE_HOST" \
  "bash -s" <<<"$remote_script"

echo "--> verifying $OPS_USER@$REMOTE_HOST"
verify_key="${OPS_PROBE_KEY:-}"
if [ -z "$verify_key" ]; then
  # Fall back to probing with the root key — unlikely to succeed for ops but
  # worth a readable error instead of silent success.
  verify_key="$REMOTE_ROOT_KEY"
fi
if probe_ops "$verify_key" >/dev/null; then
  echo "ok: $OPS_USER@$REMOTE_HOST is reachable with passwordless sudo"
  exit 0
fi
echo "error: provisioning completed but $OPS_USER@$REMOTE_HOST still unreachable" >&2
exit 2
