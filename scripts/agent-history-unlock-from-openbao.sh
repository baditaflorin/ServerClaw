#!/usr/bin/env bash
# Unlock the agent-history data volume by hand, with no tools to install and nothing to type (ADR 0494).
#
# Run it on the operator's Mac. It uses the two ssh aliases that already route through the Proxmox host:
#   0mcp_runtime_control  where OpenBao runs (the passphrase is read there, over its loopback address)
#   0mcp_agent_history    the guest with the locked volume (agent-history-unlock opens, mounts and starts the store)
# The OpenBao `ops` password is read from the operator's checkout (.local/openbao/ops-password.txt) and goes to the remote reader on
# standard input only. The passphrase travels through one pipe, from the first ssh into the second; it is never shown, never an
# argument or an environment variable, and never written to a file. Re-running is safe: a volume that is already unlocked is left alone.
#
# Usage:  bash scripts/agent-history-unlock-from-openbao.sh [path-to-ops-password-file]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
reader="$here/agent-history-openbao-read.py"
# The OpenBao converge reads its passwords from the PRIMARY checkout's .local/openbao (repo_shared_local_root), which is where the
# `ops` user's current password lives; other checkouts can hold older copies that OpenBao rejects.
password_file="${1:-${OPENBAO_OPS_PASSWORD_FILE:-$HOME/Documents/GITHUB_PROJECTS/platform_server/.local/openbao/ops-password.txt}}"
oob_host="${OPENBAO_SSH_HOST:-0mcp_runtime_control}"
guest_host="${AGENT_HISTORY_SSH_HOST:-0mcp_agent_history}"
# OpenBao as the guest of runtime-control sees it (loopback); the override exists for tests only.
address="${OPENBAO_ADDRESS:-http://127.0.0.1:8201}"
[[ "$address" =~ ^https?://[A-Za-z0-9._:-]+$ ]] || { echo "OPENBAO_ADDRESS is not a plain http(s) address" >&2; exit 2; }

[ -r "$reader" ] || { echo "missing $reader" >&2; exit 2; }
[ -r "$password_file" ] || { echo "cannot read the OpenBao ops password file: $password_file (pass its path as the first argument)" >&2; exit 2; }

# The reader source travels as base64 (it holds no secret), so the password can use the ssh standard input alone.
encoded="$(base64 < "$reader" | tr -d '\n')"
remote="python3 -c 'import base64,sys; ns={\"__name__\":\"lib\"}; exec(base64.b64decode(sys.argv[1]), ns); ns[\"main\"](sys.argv[2:])' $encoded $address"

echo "agent-history-unlock-from-openbao: reading the passphrase from OpenBao via $oob_host (the value is never printed)"
ssh -T -o BatchMode=yes "$oob_host" "$remote" < "$password_file" \
  | ssh -T -o BatchMode=yes "$guest_host" "sudo -n /usr/local/sbin/agent-history-unlock"
