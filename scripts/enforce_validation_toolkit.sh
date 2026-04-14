#!/bin/bash
# ADR 0369: Enforce validation_toolkit ownership
# Canonical validator names may only be defined in scripts/validation_toolkit.py.

set -e

REPO_ROOT=$(git rev-parse --show-toplevel)
MODE="${1:-}"

case "$MODE" in
  "")
    FILES=$(git -C "$REPO_ROOT" diff --cached --name-only --diff-filter=ACM -- 'scripts/*.py' 'scripts/**/*.py' || true)
    ;;
  --all-files)
    FILES=$(git -C "$REPO_ROOT" ls-files -- 'scripts/*.py' 'scripts/**/*.py' || true)
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
