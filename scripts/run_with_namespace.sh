#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_ID_VALUE="${LV3_RUN_ID:-${RUN_ID:-}}"

if [[ -n "$RUN_ID_VALUE" ]]; then
  eval "$(
    "$PYTHON_BIN" "$REPO_ROOT/scripts/run_namespace.py" \
      --repo-root "$REPO_ROOT" \
      --run-id "$RUN_ID_VALUE" \
      --ensure \
      --format shell
  )"
else
  eval "$(
    "$PYTHON_BIN" "$REPO_ROOT/scripts/run_namespace.py" \
      --repo-root "$REPO_ROOT" \
      --ensure \
      --format shell
  )"
fi

export LV3_RUN_ID
export LV3_RUN_SLUG
export LV3_RUN_NAMESPACE_ROOT
export LV3_RUN_ANSIBLE_DIR
export LV3_RUN_ANSIBLE_TMP_DIR
export LV3_RUN_ANSIBLE_RETRY_DIR
export LV3_RUN_ANSIBLE_CONTROL_PATH_DIR
export LV3_RUN_TOFU_DIR
export LV3_RUN_RENDERED_DIR
export LV3_RUN_LOGS_DIR
export LV3_RUN_RECEIPTS_DIR
export LV3_RUN_ANSIBLE_LOG_PATH

export ANSIBLE_LOCAL_TEMP="${ANSIBLE_LOCAL_TEMP:-$LV3_RUN_ANSIBLE_TMP_DIR}"
export ANSIBLE_RETRY_FILES_SAVE_PATH="${ANSIBLE_RETRY_FILES_SAVE_PATH:-$LV3_RUN_ANSIBLE_RETRY_DIR}"
export ANSIBLE_SSH_CONTROL_PATH_DIR="${ANSIBLE_SSH_CONTROL_PATH_DIR:-$LV3_RUN_ANSIBLE_CONTROL_PATH_DIR}"
export ANSIBLE_LOG_PATH="${ANSIBLE_LOG_PATH:-$LV3_RUN_ANSIBLE_LOG_PATH}"
export TOFU_PLAN_DIR="${TOFU_PLAN_DIR:-$LV3_RUN_TOFU_DIR}"

exec "$@"
