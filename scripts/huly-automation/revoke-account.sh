#!/usr/bin/env bash
# Soft-revoke a Huly account's access to a workspace by downgrading its role
# to the lowest privilege (DocGuest). Authorization is re-checked from the DB
# on every request, so this takes effect immediately even for already-issued
# tokens (see generate-token.sh) — there is no per-token revocation list in
# this Huly version.
#
# For full fleet-wide revocation (invalidates every session, not just this
# account), see rotate-secret.sh instead.
#
# Usage: revoke-account.sh <email> <workspace-slug>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <email> <workspace-slug>" >&2
  exit 1
fi

email="$1"; workspace="$2"

echo "downgrading $email in workspace $workspace to DocGuest (lowest privilege)"
huly_tool_run -- bundle.js set-user-role "$email" "$workspace" DocGuest
echo "done. To fully remove membership, use the Huly UI: Settings -> Members -> remove."
