#!/usr/bin/env bash
# Shared helpers for scripts/huly-automation/*.sh
# managed-by: role=huly_runtime adr=0419
set -euo pipefail

# .local/ only exists in the main checkout, not in git worktrees (see
# CLAUDE.md — "Worktrees intentionally lack .local/"), so resolve the main
# repo root via git's common-dir rather than a path relative to this script.
_HULY_MAIN_REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --path-format=absolute --git-common-dir 2>/dev/null | xargs dirname)"
HULY_SSH_CONFIG="${HULY_SSH_CONFIG:-${_HULY_MAIN_REPO_ROOT}/.local/ssh/claude-ops.config}"
HULY_SSH_ALIAS="${HULY_SSH_ALIAS:-claude-ops-docker-runtime}"
HULY_REMOTE_ENV_FILE="${HULY_REMOTE_ENV_FILE:-/opt/huly/.env}"
HULY_DOCKER_NETWORK="${HULY_DOCKER_NETWORK:-huly_huly_net}"

if [[ ! -f "$HULY_SSH_CONFIG" ]]; then
  echo "error: SSH config not found at $HULY_SSH_CONFIG (set HULY_SSH_CONFIG to override)" >&2
  exit 1
fi

huly_ssh() {
  ssh -F "$HULY_SSH_CONFIG" "$HULY_SSH_ALIAS" "$@"
}

# Runs `hardcoreeng/tool` on the guest, on the huly network, with the live
# SECRET/CR_DB_URL/HULY_VERSION sourced from /opt/huly/.env.
#
# Builds ONE fully shell-quoted command string locally (each argument passed
# through `printf %q`) and hands it to ssh as a single argument, so the
# remote shell only parses it once — safe for passwords/names containing
# spaces or shell metacharacters.
#
# Usage: huly_tool_run -- bundle.js <command> [args...]
huly_tool_run() {
  local quoted_args=""
  local a
  for a in "$@"; do
    quoted_args+=" $(printf '%q' "$a")"
  done

  # /opt/huly/.env is root-only (mode 0600), so this has to run as root.
  # It also contains a raw JSON value (GOOGLE_CREDENTIALS=...) that breaks a
  # plain `bash source` — docker compose's env-file parser tolerates that,
  # bash's script parser doesn't. Pull out just the keys we need with grep
  # instead of sourcing the whole file.
  local remote_script
  remote_script=$(cat <<EOF
set -euo pipefail
env_line() { grep "^\$1=" '$HULY_REMOTE_ENV_FILE' | head -n1 | cut -d= -f2-; }
SECRET="\$(env_line SECRET)"
CR_DB_URL="\$(env_line CR_DB_URL)"
HULY_VERSION="\$(env_line HULY_VERSION)"
docker run --rm \\
  --network '$HULY_DOCKER_NETWORK' \\
  -e SERVER_SECRET="\$SECRET" \\
  -e ACCOUNTS_URL="http://account:3000" \\
  -e TRANSACTOR_URL="ws://transactor:3333" \\
  -e DB_URL="\$CR_DB_URL" \\
  -e ACCOUNT_DB_URL="\$CR_DB_URL" \\
  -e QUEUE_CONFIG="redpanda:9092" \\
  -e STORAGE_CONFIG="minio|minio?accessKey=minioadmin&secretKey=minioadmin" \\
  "hardcoreeng/tool:\${HULY_VERSION}"$quoted_args
EOF
)
  huly_ssh "sudo bash -c $(printf '%q' "$remote_script")"
}
