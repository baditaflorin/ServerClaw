#!/bin/bash
# ADR 0369: Enforce validation_toolkit ownership
# Canonical validator names may only be defined in scripts/validation_toolkit.py.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v git >/dev/null 2>&1 && git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
else
  # Immutable remote-validation snapshots intentionally omit .git. The script
  # path remains a trustworthy repository anchor for content-only checks.
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
MODE="${1:-}"

git_metadata_available() {
  command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

case "$MODE" in
  "")
    if git_metadata_available; then
      FILES=$(git -C "$REPO_ROOT" diff --cached --name-only --diff-filter=ACM -- 'scripts/*.py' 'scripts/**/*.py' || true)
    else
      # The default mode is intentionally a no-op without Git metadata: it
      # checks staged files, and snapshots have no staging area.
      FILES=""
    fi
    ;;
  --all-files)
    if git_metadata_available; then
      FILES=$(git -C "$REPO_ROOT" ls-files -- 'scripts/*.py' 'scripts/**/*.py' || true)
    else
      FILES=$(find "$REPO_ROOT/scripts" -type f -name '*.py' ! -path '*/__pycache__/*' -print \
        | LC_ALL=C sort \
        | sed "s#^$REPO_ROOT/##")
    fi
    ;;
  *)
    echo "Usage: scripts/enforce_validation_toolkit.sh [--all-files]" >&2
    exit 2
    ;;
esac

if [ -z "$FILES" ]; then
  exit 0
fi

FAILED=0
TOOLKIT_PATTERN='^def (require_mapping|require_str|require_string_list|require_unique_string_list|require_list|require_bool|require_int|require_identifier|require_http_url|require_semver|require_enum|require_path)\b'

for file in $FILES; do
  filepath="$REPO_ROOT/$file"
  basename_file=$(basename "$file")

  # Skip the toolkit itself and test file
  if [ "$basename_file" = "validation_toolkit.py" ] || [ "$basename_file" = "test_validation_toolkit.py" ]; then
    continue
  fi

  while IFS= read -r match; do
    [ -z "$match" ] && continue
    func=${match#def }
    if [ -n "$func" ]; then
      echo "❌ $file: redefines shared validator '$func'"
      echo "   Canonical validator names may only be defined in scripts/validation_toolkit.py"
      echo "   Rename the local helper or compose it from validation_toolkit imports"
      FAILED=1
    fi
  done < <(grep -Eo "$TOOLKIT_PATTERN" "$filepath" || true)
done

if [ $FAILED -eq 1 ]; then
  echo ""
  echo "ERROR: Canonical validation helpers must stay centralized in validation_toolkit (ADR 0369)"
  echo "See docs/adr/0369-python-validation-toolkit.md for details"
  exit 1
fi

exit 0
