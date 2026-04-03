#!/usr/bin/env bash

set -euo pipefail

PYTHON_BIN="${LV3_VALIDATE_PYTHON_BIN:-}"

resolve_python_bin() {
  local candidate=""

  if [[ -n "$PYTHON_BIN" ]]; then
    return 0
  fi

  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      return 0
    fi
  done

  echo "Missing Python interpreter for validation helper." >&2
  exit 1
}

module_name_for_package() {
  case "$1" in
    pyyaml)
      echo "yaml"
      ;;
    nats-py)
      echo "nats"
      ;;
    ansible-core)
      echo "ansible"
      ;;
    *)
      echo "${1//-/_}"
      ;;
  esac
}

module_available() {
  local module_name="$1"
  "$PYTHON_BIN" - "$module_name" <<'PY' >/dev/null 2>&1
import importlib.util
import sys
from pathlib import Path

module_name = sys.argv[1]
spec = importlib.util.find_spec(module_name)
if spec is None:
    raise SystemExit(1)

workspace = Path.cwd().resolve()
candidate_paths = []
if spec.origin not in {None, "built-in", "frozen"}:
    candidate_paths.append(Path(spec.origin).resolve())
for location in spec.submodule_search_locations or ():
    candidate_paths.append(Path(location).resolve())

if candidate_paths and all(path == workspace or workspace in path.parents for path in candidate_paths):
    raise SystemExit(1)

raise SystemExit(0)
PY
}

install_missing_packages() {
  local missing_packages=("$@")
  local install_args=(
    -m
    pip
    install
    --quiet
    --disable-pip-version-check
  )

  if "$PYTHON_BIN" -m pip --help 2>/dev/null | grep -q -- "--break-system-packages"; then
    install_args+=(--break-system-packages)
  fi

  "$PYTHON_BIN" "${install_args[@]}" "${missing_packages[@]}"
}

main() {
  local packages=()
  local missing_packages=()
  local package=""
  local module_name=""
  local uv_args=()

  resolve_python_bin

  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--" ]]; then
      shift
      break
    fi
    packages+=("$1")
    shift
  done

  if [[ $# -eq 0 ]]; then
    echo "Usage: run_python_with_packages.sh [package ...] -- <python-args...>" >&2
    exit 1
  fi

  if command -v uv >/dev/null 2>&1; then
    for package in "${packages[@]}"; do
      uv_args+=(--with "$package")
    done
    exec uv run "${uv_args[@]}" python3 "$@"
  fi

  for package in "${packages[@]}"; do
    module_name="$(module_name_for_package "$package")"
    if ! module_available "$module_name"; then
      missing_packages+=("$package")
    fi
  done

  if [[ ${#missing_packages[@]} -gt 0 ]]; then
    install_missing_packages "${missing_packages[@]}"
  fi

  exec "$PYTHON_BIN" "$@"
}

main "$@"
