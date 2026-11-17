#!/usr/bin/env bash
# One-time setup of the unattended unlock of the agent-history data volume (ADR 0494, amendment 2026-11-12).
#
# Run it on the operator's Mac, once. Nothing to install and nothing to type. It:
#   1. logs in to OpenBao as the `ops` administrator (password read from the primary checkout, sent on standard input only),
#   2. creates the policy (read on the passphrase entry only) and the AppRole `agent-history-unlock`, and issues a login for it,
#   3. pipes that login straight into two root-only files on the agent-history guest (luks_role_id, luks_secret_id),
#   4. checks that the guest can now fetch the passphrase by itself: it prints only the NUMBER of bytes fetched, never the value.
# No secret is printed, an argument, an environment variable or a file on this Mac. Re-running is safe (a new secret_id is issued).
#
# Prerequisite: the helpers and the boot unit are installed on the guest (the role of PR #696, or installed by hand the same way).
#
# Usage:  bash scripts/agent-history-setup-unattended-unlock.sh [path-to-ops-password-file]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
admin="$here/agent-history-openbao-admin.py"
deliver="$here/agent-history-deliver-approle.py"
password_file="${1:-${OPENBAO_OPS_PASSWORD_FILE:-$HOME/Documents/GITHUB_PROJECTS/platform_server/.local/openbao/ops-password.txt}}"
oob_host="${OPENBAO_SSH_HOST:-0mcp_runtime_control}"
guest_host="${AGENT_HISTORY_SSH_HOST:-0mcp_agent_history}"
address="${OPENBAO_ADDRESS:-http://127.0.0.1:8201}"
guest_dir="${AGENT_HISTORY_OPENBAO_DIR:-/opt/agent-history/openbao}"
guest_sudo="${AGENT_HISTORY_SUDO:-sudo -n}"
guest_fetcher="${AGENT_HISTORY_LUKS_FETCHER:-/usr/local/sbin/agent-history-luks-passphrase}"  # a test seam
prefix="${OPENBAO_POLICY_PREFIX:-0mcp}"
[[ "$address" =~ ^https?://[A-Za-z0-9._:-]+$ ]] || { echo "OPENBAO_ADDRESS is not a plain http(s) address" >&2; exit 2; }
[[ "$prefix" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "OPENBAO_POLICY_PREFIX is not a plain word" >&2; exit 2; }
[[ "$guest_dir" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "AGENT_HISTORY_OPENBAO_DIR is not a plain path" >&2; exit 2; }

for f in "$admin" "$deliver"; do [ -r "$f" ] || { echo "missing $f" >&2; exit 2; }; done
[ -r "$password_file" ] || { echo "cannot read the OpenBao ops password file: $password_file (pass its path as the first argument)" >&2; exit 2; }

# The helper sources travel as base64 (they hold no secret), so the password and the AppRole login can use standard input alone.
run_py() {  # run_py <file> <args...>   -> a command line that runs the file's main(argv) from a base64 argument
  local encoded; encoded="$(base64 < "$1" | tr -d '\n')"; shift
  printf "python3 -c 'import base64,sys; ns={\"__name__\":\"lib\"}; exec(base64.b64decode(sys.argv[1]), ns); ns[\"main\"](sys.argv[2:])' %s %s" "$encoded" "$*"
}

echo "agent-history-setup: creating the OpenBao policy and AppRole via $oob_host, delivering them to $guest_host (no secret is printed)"
ssh -T -o BatchMode=yes "$oob_host" "$(run_py "$admin" "$address" ops "$prefix")" < "$password_file" \
  | ssh -T -o BatchMode=yes "$guest_host" "$guest_sudo $(run_py "$deliver" "$guest_dir")"

echo "agent-history-setup: checking that the guest can fetch the passphrase by itself (prints the byte count only)"
count="$(ssh -T -o BatchMode=yes "$guest_host" "$guest_sudo $guest_fetcher | wc -c" | tr -d ' ')"
if [ "${count:-0}" -gt 0 ]; then
  echo "agent-history-setup: OK, the guest fetched ${count} bytes from OpenBao with the new login. The next reboot unlocks the volume by itself."
else
  echo "agent-history-setup: the guest could not fetch the passphrase (0 bytes). See the message above; the manual unlock still works." >&2
  exit 1
fi
