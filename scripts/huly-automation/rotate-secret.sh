#!/usr/bin/env bash
# NUCLEAR OPTION: rotate the shared Huly instance SECRET.
#
# This invalidates every previously issued API token (see generate-token.sh)
# AND logs out every human user's active session — not just one automation
# account. Only use this for genuine credential compromise; for revoking a
# single bot/integration, use revoke-account.sh instead.
#
# Mechanics: the huly_runtime Ansible role persists the secret once-only
# (`force: false`) on both the guest and the local mirror in
# .local/huly/huly-secret. Rotation = delete both copies, then reconverge so
# a fresh secret is generated and every service picks it up.
#
# Usage: rotate-secret.sh   (interactive confirmation required)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./_lib.sh

REPO_ROOT="$(cd ../.. && pwd)"
LOCAL_SECRET_FILE="$REPO_ROOT/.local/huly/huly-secret"
# Derived from huly_runtime's secret_dir default: /etc/<unix_prefix>/huly,
# where unix_prefix = platform_domain's first label (see identity.yml).
# Override with HULY_REMOTE_SECRET_FILE= if your deployment differs.
REMOTE_SECRET_FILE="${HULY_REMOTE_SECRET_FILE:-/etc/0mcp/huly/huly-secret}"

echo "This will invalidate ALL Huly sessions and API tokens fleet-wide."
read -r -p "Type 'rotate-huly-secret' to confirm: " confirm
if [[ "$confirm" != "rotate-huly-secret" ]]; then
  echo "aborted."
  exit 1
fi

echo "removing local secret mirror: $LOCAL_SECRET_FILE"
rm -f "$LOCAL_SECRET_FILE"

echo "removing remote secret file: $REMOTE_SECRET_FILE"
huly_ssh "sudo rm -f '$REMOTE_SECRET_FILE'"

cat <<'EOF'

Done. The secret files are gone; the next `make converge-huly` (from
.claude/worktrees/pm-tools-deploy/) will generate a fresh SECRET and roll it
out to every Huly container. All existing tokens and logged-in sessions stop
working the moment that converge completes.
EOF
