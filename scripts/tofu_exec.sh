#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TOFU_IMAGE="${TOFU_IMAGE:-registry.example.com/check-runner/infra:2026.03.23}"
TOFU_PLATFORM="${TOFU_PLATFORM:-linux/amd64}"
TOFU_WORKSPACE="${TOFU_WORKSPACE:-/workspace}"
TOFU_INIT_BACKEND="${TOFU_INIT_BACKEND:-auto}"
TOFU_DOCKER_NETWORK="${TOFU_DOCKER_NETWORK:-}"

LV3_RUN_ID="${LV3_RUN_ID:-${RUN_ID:-}}"
if [[ -n "$LV3_RUN_ID" ]]; then
  eval "$(
    "$PYTHON_BIN" "$REPO_ROOT/scripts/run_namespace.py" \
      --repo-root "$REPO_ROOT" \
      --run-id "$LV3_RUN_ID" \
      --ensure \
      --format shell
  )"
fi
TOFU_PLAN_DIR="${TOFU_PLAN_DIR:-${LV3_RUN_TOFU_DIR:-$REPO_ROOT/.local/tofu-plans}}"

usage() {
  cat <<'EOF'
Usage:
  scripts/tofu_exec.sh validate [all|production|staging]
  scripts/tofu_exec.sh init <environment>
  scripts/tofu_exec.sh plan <environment>
  scripts/tofu_exec.sh apply <environment>
  scripts/tofu_exec.sh drift <environment>
  scripts/tofu_exec.sh import <environment> <resource-address> <import-id>
  scripts/tofu_exec.sh show <environment> <state-address>
EOF
}

environment_dir() {
  local environment="${1:-}"

  case "$environment" in
    production|staging)
      printf '%s\n' "tofu/environments/$environment"
      ;;
    *)
      echo "unknown OpenTofu environment: $environment" >&2
      exit 1
      ;;
  esac
}

append_env() {
  local name="$1"
  local value="${!name:-}"

  if [[ -n "$value" ]]; then
    DOCKER_ARGS+=("-e" "$name=$value")
  fi
}

write_cli_config() {
  local workdir="$1"
  local cli_config="$TOFU_PLAN_DIR/tofu.tfrc"
  local provider_path=""

  if [[ "$workdir" = /* ]]; then
    provider_path="$workdir/.terraform/providers"
  else
    provider_path="$TOFU_WORKSPACE/$workdir/.terraform/providers"
  fi

  if [[ ! -d "$REPO_ROOT/$workdir/.terraform/providers" && ! -d "$workdir/.terraform/providers" ]]; then
    cat >"$cli_config" <<'EOF'
provider_installation {
  direct {}
}
EOF
    return 0
  fi

  cat >"$cli_config" <<EOF
provider_installation {
  filesystem_mirror {
    path = "$provider_path"
  }

  direct {
    exclude = ["registry.opentofu.org/bpg/proxmox"]
  }
}
EOF
}

run_tofu() {
  local workdir="$1"
  shift

  write_cli_config "$workdir"

  local container_workdir="$TOFU_WORKSPACE/$workdir"
  if [[ "$workdir" = /* ]]; then
    container_workdir="$workdir"
  fi

  local -a DOCKER_ARGS=(
    docker run --rm
    --platform "$TOFU_PLATFORM"
    -v "$REPO_ROOT:$TOFU_WORKSPACE"
    -v "$TOFU_PLAN_DIR:/plans"
    -w "$container_workdir"
  )

  if [[ -n "$TOFU_DOCKER_NETWORK" ]]; then
    DOCKER_ARGS+=(--network "$TOFU_DOCKER_NETWORK")
  fi

  append_env TF_VAR_proxmox_endpoint
  append_env TF_VAR_proxmox_api_token
  append_env AWS_ACCESS_KEY_ID
  append_env AWS_SECRET_ACCESS_KEY
  append_env AWS_SESSION_TOKEN
  append_env AWS_DEFAULT_REGION
  append_env AWS_REGION
  append_env AWS_ENDPOINT_URL
  append_env AWS_ENDPOINT_URL_S3
  DOCKER_ARGS+=("-e" "TF_CLI_CONFIG_FILE=/plans/tofu.tfrc")

  DOCKER_ARGS+=("$TOFU_IMAGE" tofu "$@")
  "${DOCKER_ARGS[@]}"
}

validate_environment() {
  local environment="$1"
  local env_dir

  env_dir="$(prepare_runtime_workspace "$environment" false)"
  run_tofu "$env_dir" init -backend=false -input=false >/dev/null
  run_tofu "$env_dir" validate -no-color
}

plan_path() {
  local environment="$1"
  printf '/plans/%s.tfplan\n' "$environment"
}

plan_json_path() {
  local environment="$1"
  printf '/plans/%s.plan.json\n' "$environment"
}

state_path() {
  local environment="$1"
  printf '/plans/%s.tfstate\n' "$environment"
}

use_backend() {
  case "$TOFU_INIT_BACKEND" in
    true)
      return 0
      ;;
    false)
      return 1
      ;;
    auto)
      [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]
      ;;
    *)
      echo "invalid TOFU_INIT_BACKEND value: $TOFU_INIT_BACKEND" >&2
      exit 1
      ;;
  esac
}

init_args() {
  if use_backend; then
    printf '%s\n' -input=false
  else
    printf '%s\n' -backend=false -input=false
  fi
}

state_args() {
  local environment="$1"

  if use_backend; then
    return 0
  fi

  printf '%s\n' "-state=$(state_path "$environment")"
}

prepare_runtime_workspace() {
  local environment="$1"
  local keep_backend="${2:-true}"
  local runtime_root="$TOFU_PLAN_DIR/runtime"
  local runtime_env="$runtime_root/tofu/environments/$environment"

  mkdir -p "$runtime_root"
  rsync -a --delete "$REPO_ROOT/tofu/" "$runtime_root/tofu/"
  rsync -a --delete "$REPO_ROOT/keys/" "$runtime_root/keys/"
  if [[ "$keep_backend" != "true" ]]; then
    rm -f "$runtime_env/backend.tf"
  fi
  printf '/plans/runtime/tofu/environments/%s\n' "$environment"
}

ensure_initialized() {
  local env_dir="$1"
  local -a init_cli_args=()

  mapfile -t init_cli_args < <(init_args)
  run_tofu "$env_dir" init "${init_cli_args[@]}"
}

action="${1:-}"
shift || true

mkdir -p "$TOFU_PLAN_DIR"

case "$action" in
  validate)
    target="${1:-all}"
    case "$target" in
      all)
        validate_environment production
        validate_environment staging
        ;;
      production|staging)
        validate_environment "$target"
        ;;
      *)
        echo "unknown validation target: $target" >&2
        exit 1
        ;;
    esac
    ;;
  init)
    environment="${1:-}"
    [[ -n "$environment" ]] || { usage >&2; exit 1; }
    if use_backend; then
      env_dir="$(prepare_runtime_workspace "$environment" true)"
    else
      env_dir="$(prepare_runtime_workspace "$environment" false)"
    fi
    ensure_initialized "$env_dir"
    ;;
  plan)
    environment="${1:-}"
    [[ -n "$environment" ]] || { usage >&2; exit 1; }
    if use_backend; then
      env_dir="$(prepare_runtime_workspace "$environment" true)"
    else
      env_dir="$(prepare_runtime_workspace "$environment" false)"
    fi
    plan_file="$(plan_path "$environment")"
    mapfile -t state_cli_args < <(state_args "$environment")
    ensure_initialized "$env_dir"
    run_tofu "$env_dir" plan "${state_cli_args[@]}" -input=false -lock-timeout=60s -out="$plan_file"
    run_tofu "$env_dir" show -json "$plan_file" > "$TOFU_PLAN_DIR/${environment}.plan.json"
    echo "saved plan to $TOFU_PLAN_DIR/${environment}.tfplan"
    echo "saved plan json to $TOFU_PLAN_DIR/${environment}.plan.json"
    ;;
  apply)
    environment="${1:-}"
    [[ -n "$environment" ]] || { usage >&2; exit 1; }
    if use_backend; then
      env_dir="$(prepare_runtime_workspace "$environment" true)"
    else
      env_dir="$(prepare_runtime_workspace "$environment" false)"
    fi
    plan_file="$(plan_path "$environment")"
    if [[ ! -f "$TOFU_PLAN_DIR/${environment}.tfplan" ]]; then
      echo "missing saved plan: $TOFU_PLAN_DIR/${environment}.tfplan" >&2
      exit 1
    fi
    mapfile -t state_cli_args < <(state_args "$environment")
    ensure_initialized "$env_dir"
    run_tofu "$env_dir" apply "${state_cli_args[@]}" -input=false "$plan_file"
    ;;
  drift)
    environment="${1:-}"
    [[ -n "$environment" ]] || { usage >&2; exit 1; }
    if use_backend; then
      env_dir="$(prepare_runtime_workspace "$environment" true)"
    else
      env_dir="$(prepare_runtime_workspace "$environment" false)"
    fi
    plan_file="$(plan_path "$environment")"
    mapfile -t state_cli_args < <(state_args "$environment")
    ensure_initialized "$env_dir"
    set +e
    run_tofu "$env_dir" plan "${state_cli_args[@]}" -input=false -detailed-exitcode -lock-timeout=60s -out="$plan_file"
    rc=$?
    set -e
    run_tofu "$env_dir" show -json "$plan_file" > "$TOFU_PLAN_DIR/${environment}.plan.json"
    exit "$rc"
    ;;
  import)
    environment="${1:-}"
    resource_address="${2:-}"
    import_id="${3:-}"
    [[ -n "$environment" && -n "$resource_address" && -n "$import_id" ]] || { usage >&2; exit 1; }
    if use_backend; then
      env_dir="$(prepare_runtime_workspace "$environment" true)"
    else
      env_dir="$(prepare_runtime_workspace "$environment" false)"
    fi
    mapfile -t state_cli_args < <(state_args "$environment")
    ensure_initialized "$env_dir"
    run_tofu "$env_dir" import "${state_cli_args[@]}" -input=false "$resource_address" "$import_id"
    ;;
  show)
    environment="${1:-}"
    state_address="${2:-}"
    [[ -n "$environment" && -n "$state_address" ]] || { usage >&2; exit 1; }
    if use_backend; then
      env_dir="$(prepare_runtime_workspace "$environment" true)"
    else
      env_dir="$(prepare_runtime_workspace "$environment" false)"
    fi
    mapfile -t state_cli_args < <(state_args "$environment")
    ensure_initialized "$env_dir"
    run_tofu "$env_dir" state show "${state_cli_args[@]}" "$state_address"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
