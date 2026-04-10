#!/bin/bash
# ADR 0369: Enforce validation_toolkit pattern
# Ensures all scripts with validation functions use the shared toolkit

set -e

REPO_ROOT=$(git rev-parse --show-toplevel)
TOOLKIT="$REPO_ROOT/scripts/validation_toolkit.py"
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep "scripts/.*\.py$" || true)

if [ -z "$STAGED_FILES" ]; then
  exit 0
fi

# Functions that must be imported from validation_toolkit, not redefined
TOOLKIT_FUNCTIONS=(
  "require_mapping"
  "require_str"
  "require_string_list"
  "require_list"
  "require_bool"
  "require_int"
  "require_identifier"
  "require_http_url"
  "require_semver"
  "require_enum"
  "require_path"
)

FAILED=0

for file in $STAGED_FILES; do
  filepath="$REPO_ROOT/$file"
  basename_file=$(basename "$file")

  # Skip the toolkit itself and test file
  if [ "$basename_file" = "validation_toolkit.py" ] || [ "$basename_file" = "test_validation_toolkit.py" ]; then
    continue
  fi

  # Check if file defines any toolkit functions
  for func in "${TOOLKIT_FUNCTIONS[@]}"; do
    if grep -q "^def $func" "$filepath"; then
      # File defines a toolkit function - it must import from validation_toolkit
      if ! grep -q "from validation_toolkit import" "$filepath"; then
        echo "❌ $file: defines '$func' but doesn't import from validation_toolkit"
        echo "   Add: from validation_toolkit import $func"
        FAILED=1
      fi
    fi
  done
done

if [ $FAILED -eq 1 ]; then
  echo ""
  echo "ERROR: Scripts must import base validators from validation_toolkit (ADR 0369)"
  echo "See docs/adr/0369-python-validation-toolkit.md for details"
  exit 1
fi

exit 0
