#!/usr/bin/env bash
# Create a dedicated Huly automation account and assign it to a workspace.
# Usage: create-account.sh <email> <first-name> <last-name> <password> <workspace-slug>
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

if [[ $# -ne 5 ]]; then
  echo "usage: $0 <email> <first-name> <last-name> <password> <workspace-slug>" >&2
  exit 1
fi

email="$1"; first="$2"; last="$3"; password="$4"; workspace="$5"

echo "creating account: $email ($first $last)"
huly_tool_run -- bundle.js create-account "$email" -p "$password" -f "$first" -l "$last"

echo "assigning $email to workspace: $workspace"
huly_tool_run -- bundle.js assign-workspace "$email" "$workspace"

echo "done. Next: scripts/huly-automation/generate-token.sh $email $workspace"
