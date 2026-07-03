#!/usr/bin/env bash
# Mint a signed API token (JWT) for a Huly account, scoped to a workspace.
# This is the closest thing Huly has to an "API key" — use it as the `token`
# field to @hcengineering/api-client's connect(), no password needed at runtime.
#
# Usage: generate-token.sh <email> <workspace-slug> [--admin]
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <email> <workspace-slug> [--admin]" >&2
  exit 1
fi

email="$1"; workspace="$2"; admin_flag="${3:-}"

if [[ "$admin_flag" == "--admin" ]]; then
  huly_tool_run -- bundle.js generate-token "$email" "$workspace" --admin
else
  huly_tool_run -- bundle.js generate-token "$email" "$workspace"
fi
