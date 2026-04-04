#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMMON_DIR="$(git -C "${REPO_ROOT}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"

if [[ -n "${COMMON_DIR}" ]]; then
  COMMON_REPO_ROOT="$(dirname "${COMMON_DIR}")"
else
  COMMON_REPO_ROOT="${REPO_ROOT}"
fi

printf '%s\n' "${COMMON_REPO_ROOT}/.local"
