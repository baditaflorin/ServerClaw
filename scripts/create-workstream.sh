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

readarray -t WORKSTREAM_FIELDS < <(
  python3 - "$REPO_ROOT" "$WORKSTREAM_ID" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1])
workstream_id = sys.argv[2]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "scripts"))

from platform.workstream_registry import find_workstream

record = find_workstream(workstream_id, repo_root=repo_root, include_archive=True)
if record is None:
    raise SystemExit(f"Unknown workstream: {workstream_id}")
workstream = record.payload
print(workstream["branch"])
print(workstream["worktree_path"])
print(workstream["doc"])
PY
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
