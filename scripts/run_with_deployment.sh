#!/usr/bin/env bash
# run_with_deployment.sh — ADR 0448
#
# Resolve the active (or --deployment <slug>) deployment, export the
# connection.yml env block (LV3_PROXMOX_HOST_*, LV3_BOOTSTRAP_SSH_*,
# PLATFORM_IDENTITY_OVERLAY, …), then exec the inner command with that
# environment.
#
# Usage:
#   scripts/run_with_deployment.sh [--deployment <slug>] [--quiet] -- <command...>
#
# Examples:
#   # Converge the public-edge playbook against the 0fork.com deployment:
#   scripts/run_with_deployment.sh --deployment 0fork -- \
#       make configure-edge-publication env=production
#
#   # Use the active deployment (resolved via deployment.py):
#   scripts/run_with_deployment.sh -- ansible-playbook -i inventory/hosts.yml \
#       playbooks/public-edge.yml
#
# The wrapper does NOT modify Make targets, inventory, or any committed
# file — it composes with whatever Multi-deployment Make plumbing
# ws-0445/0446 ship next. Inner commands receive the resolved env vars
# in addition to whatever the parent shell already exported (parent env
# wins on conflict so operators retain manual overrides).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

slug=""
quiet=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deployment)
      slug="${2:-}"
      shift 2
      ;;
    --deployment=*)
      slug="${1#*=}"
      shift
      ;;
    --quiet)
      quiet=1
      shift
      ;;
    --)
      shift
      break
      ;;
    --help|-h)
      sed -n '2,25p' "$0"
      exit 0
      ;;
    *)
      # Treat the first non-flag argument as the start of the command.
      break
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "run_with_deployment.sh: no command given. Use '-- <cmd...>' to run." >&2
  exit 64
fi

slug_arg=()
if [[ -n "$slug" ]]; then
  slug_arg=(--slug "$slug")
fi

# Emit the env block via the deployment CLI in shell-export form, then
# source it. We use 'shell' format (export KEY='quoted-value') so values
# with spaces or special chars survive sourcing.
env_block="$(uv run --quiet --with pyyaml --with jsonschema python3 \
  "$REPO_ROOT/scripts/deployment.py" connection "${slug_arg[@]}" \
  --format shell 2>&1)" || {
    rc=$?
    if [[ $quiet -eq 0 ]]; then
      printf '%s\n' "$env_block" >&2
    fi
    exit "$rc"
}

if [[ -n "$env_block" ]]; then
  # shellcheck disable=SC1091,SC2086
  eval "$env_block"
  if [[ $quiet -eq 0 ]]; then
    resolved_slug="${slug:-$(uv run --quiet --with pyyaml --with jsonschema python3 \
      "$REPO_ROOT/scripts/deployment.py" resolve --quiet 2>/dev/null || echo unknown)}"
    echo "==> deployment=$resolved_slug — ADR 0448 env exported" >&2
  fi
fi

exec "$@"
