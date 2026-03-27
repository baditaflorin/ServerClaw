#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/create-workstream.sh <workstream-id>

Example:
  scripts/create-workstream.sh adr-0011-monitoring
EOF
}

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 1
fi

WORKSTREAM_ID="$1"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY_PATH="$REPO_ROOT/workstreams.yaml"

readarray -t WORKSTREAM_FIELDS < <(
  ruby -r yaml -e '
    registry = YAML.load_file(ARGV[0])
    workstream = registry.fetch("workstreams").find { |item| item.fetch("id") == ARGV[1] }
    abort("Unknown workstream: #{ARGV[1]}") unless workstream
    puts workstream.fetch("branch")
    puts workstream.fetch("worktree_path")
    puts workstream.fetch("doc")
  ' "$REGISTRY_PATH" "$WORKSTREAM_ID"
)

BRANCH_NAME="${WORKSTREAM_FIELDS[0]}"
WORKTREE_PATH_RAW="${WORKSTREAM_FIELDS[1]}"
WORKSTREAM_DOC="${WORKSTREAM_FIELDS[2]}"
ABS_WORKTREE_PATH="$(cd "$REPO_ROOT" && ruby -e 'puts File.expand_path(ARGV[0])' "$WORKTREE_PATH_RAW")"

if git -C "$REPO_ROOT" worktree list --porcelain | grep -Fxq "worktree $ABS_WORKTREE_PATH"; then
  cat <<EOF
Worktree already exists:
  workstream: $WORKSTREAM_ID
  branch:     $BRANCH_NAME
  path:       $ABS_WORKTREE_PATH
  doc:        $WORKSTREAM_DOC
EOF
  exit 0
fi

mkdir -p "$(dirname "$ABS_WORKTREE_PATH")"

if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
  git -C "$REPO_ROOT" worktree add "$ABS_WORKTREE_PATH" "$BRANCH_NAME"
else
  git -C "$REPO_ROOT" worktree add -b "$BRANCH_NAME" "$ABS_WORKTREE_PATH" main
fi

cat <<EOF
Created worktree:
  workstream: $WORKSTREAM_ID
  branch:     $BRANCH_NAME
  path:       $ABS_WORKTREE_PATH
  doc:        $WORKSTREAM_DOC
EOF
