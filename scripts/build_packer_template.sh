#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKER_DOCKER_IMAGE="${PACKER_DOCKER_IMAGE:-hashicorp/packer:latest}"

resolve_cache_root() {
  local candidate="${1:-}"
  local fallback="$REPO_ROOT/.packer.d"

  if [[ -n "$candidate" ]]; then
    if [[ -d "$candidate" ]]; then
      echo "$candidate"
      return
    fi
    if mkdir -p "$candidate" 2>/dev/null; then
      echo "$candidate"
      return
    fi
  fi

  mkdir -p "$fallback"
  echo "$fallback"
}

CACHE_ROOT="$(resolve_cache_root "${PACKER_CACHE_ROOT:-${PACKER_PLUGIN_PATH:-}}")"

append_var_file_args() {
  local image="$1"
  local var_file
  local candidate_files=(
    "$REPO_ROOT/packer/variables/common.pkrvars.hcl"
    "$REPO_ROOT/packer/variables/${image}.pkrvars.hcl"
    "$REPO_ROOT/packer/variables/build-server.pkrvars.hcl"
  )

  for var_file in "${candidate_files[@]}"; do
    if [[ -f "$var_file" ]]; then
      PACKER_VAR_ARGS+=("-var-file=$var_file")
      DOCKER_PACKER_VAR_ARGS+=("-var-file=${var_file#"$REPO_ROOT"/}")
    fi
  done
}

if [[ $# -ne 1 ]]; then
  echo "Usage: scripts/build_packer_template.sh <image>" >&2
  exit 1
fi

image="$1"
template_path="$REPO_ROOT/packer/templates/${image}.pkr.hcl"

if [[ ! -f "$template_path" ]]; then
  echo "Unknown Packer template: $image" >&2
  exit 1
fi

declare -a PACKER_VAR_ARGS=()
declare -a DOCKER_PACKER_VAR_ARGS=()
append_var_file_args "$image"

if command -v packer >/dev/null 2>&1; then
  (
    cd "$REPO_ROOT/packer"
    packer init "templates/${image}.pkr.hcl" >/dev/null
    packer build "${PACKER_VAR_ARGS[@]}" "templates/${image}.pkr.hcl"
  )
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: packer or docker" >&2
  exit 1
fi

docker run --rm \
  --entrypoint /bin/sh \
  -v "$REPO_ROOT:/workspace" \
  -v "$CACHE_ROOT:/root/.packer.d" \
  -w /workspace \
  "$PACKER_DOCKER_IMAGE" \
  -lc "$(printf 'packer init %q >/dev/null && packer build' "packer/templates/${image}.pkr.hcl"; printf ' %q' "${DOCKER_PACKER_VAR_ARGS[@]}"; printf ' %q' "packer/templates/${image}.pkr.hcl")"
