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

  PACKER_VAR_ARGS=()
  DOCKER_PACKER_VAR_ARGS=()
  for var_file in "${candidate_files[@]}"; do
    if [[ -f "$var_file" ]]; then
      PACKER_VAR_ARGS+=("-var-file=$var_file")
      DOCKER_PACKER_VAR_ARGS+=("-var-file=${var_file#"$REPO_ROOT"/}")
    fi
  done
}

shopt -s nullglob
templates=("$REPO_ROOT"/packer/templates/*.pkr.hcl)
if [[ ${#templates[@]} -eq 0 ]]; then
  echo "No Packer templates present"
  exit 0
fi

if ! command -v packer >/dev/null 2>&1 && ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: packer or docker" >&2
  exit 1
fi

for template_path in "${templates[@]}"; do
  template_rel="${template_path#"$REPO_ROOT"/packer/}"
  image="$(basename "$template_path" .pkr.hcl)"
  declare -a PACKER_VAR_ARGS=()
  declare -a DOCKER_PACKER_VAR_ARGS=()
  append_var_file_args "$image"
  echo "Validating ${template_rel}"
  if command -v packer >/dev/null 2>&1; then
    (
      cd "$REPO_ROOT/packer"
      packer init "$template_rel" >/dev/null
      packer validate "${PACKER_VAR_ARGS[@]}" "$template_rel"
    )
    continue
  fi
  docker run --rm \
    --entrypoint /bin/sh \
    -v "$REPO_ROOT:/workspace" \
    -v "$CACHE_ROOT:/root/.packer.d" \
    -w /workspace \
    "$PACKER_DOCKER_IMAGE" \
    -lc "$(printf 'packer init %q >/dev/null && packer validate' "packer/${template_rel}"; printf ' %q' "${DOCKER_PACKER_VAR_ARGS[@]}"; printf ' %q' "packer/${template_rel}")"
done
