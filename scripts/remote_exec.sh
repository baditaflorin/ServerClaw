#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_SERVER_CONFIG="${REMOTE_EXEC_CONFIG:-$REPO_ROOT/config/build-server.json}"
RUNNER_MANIFEST="${REMOTE_EXEC_RUNNER_MANIFEST:-$REPO_ROOT/config/check-runner-manifest.json}"
RSYNC_EXCLUDE_FILE="${REMOTE_EXEC_EXCLUDE_FILE:-$REPO_ROOT/.rsync-exclude}"
SSH_BIN="${REMOTE_EXEC_SSH_BIN:-ssh}"
RSYNC_BIN="${REMOTE_EXEC_RSYNC_BIN:-rsync}"
PYTHON_BIN="${REMOTE_EXEC_PYTHON_BIN:-python3}"
CONNECT_TIMEOUT="${REMOTE_EXEC_CONNECT_TIMEOUT:-5}"
VERBOSE="${REMOTE_EXEC_VERBOSE:-0}"
LOCAL_FALLBACK=false
COMMAND_LABEL=""

REMOTE_HOST=""
SSH_KEY_PATH=""
WORKSPACE_ROOT_BASE=""
WORKSPACE_ROOT=""
DEFAULT_TIMEOUT_SECONDS=""
DOCKER_SOCKET=""
REMOTE_COMMAND=""
LOCAL_COMMAND=""
DOCKER_IMAGE=""
RUNNER_WORKDIR=""
TIMEOUT_SECONDS=""
SKIP_DOCKER="false"
MOUNT_DOCKER_SOCKET="false"
BUILTIN_ACTION=""
SSH_OPTIONS_NL=""
BUILD_SERVER_PIP_CACHE_VOLUME=""
BUILD_SERVER_PACKER_PLUGIN_CACHE=""
BUILD_SERVER_ANSIBLE_COLLECTION_CACHE=""
BUILD_SERVER_ANSIBLE_REQUIREMENTS_SHA_FILE=""
BUILD_SERVER_APT_PROXY_URL=""
RUNNER_CACHE_MOUNTS_NL=""
LV3_SESSION_ID="${LV3_SESSION_ID:-}"
LV3_SESSION_SLUG="${LV3_SESSION_SLUG:-}"
LV3_SESSION_LOCAL_ROOT="${LV3_SESSION_LOCAL_ROOT:-}"
LV3_SESSION_NATS_PREFIX="${LV3_SESSION_NATS_PREFIX:-}"
LV3_SESSION_STATE_NAMESPACE="${LV3_SESSION_STATE_NAMESPACE:-}"
LV3_SESSION_RECEIPT_SUFFIX="${LV3_SESSION_RECEIPT_SUFFIX:-}"
LV3_REMOTE_WORKSPACE_ROOT="${LV3_REMOTE_WORKSPACE_ROOT:-}"

SSH_BASE_CMD=()

usage() {
  cat <<'EOF'
Usage:
  scripts/remote_exec.sh <command-label> [--local-fallback]

Examples:
  scripts/remote_exec.sh remote-lint
  scripts/remote_exec.sh remote-pre-push --local-fallback
  scripts/remote_exec.sh remote-exec --local-fallback
EOF
}

fail() {
  echo "remote_exec: $*" >&2
  exit 1
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --local-fallback)
        LOCAL_FALLBACK=true
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      -*)
        fail "unknown option: $1"
        ;;
      *)
        if [[ -n "$COMMAND_LABEL" ]]; then
          fail "command label already set to $COMMAND_LABEL"
        fi
        COMMAND_LABEL="$1"
        ;;
    esac
    shift
  done

  [[ -n "$COMMAND_LABEL" ]] || {
    usage >&2
    exit 1
  }
}

load_command_configuration() {
  [[ -f "$BUILD_SERVER_CONFIG" ]] || fail "missing config: $BUILD_SERVER_CONFIG"
  [[ -f "$RSYNC_EXCLUDE_FILE" ]] || fail "missing rsync exclude file: $RSYNC_EXCLUDE_FILE"

  eval "$(
    "$PYTHON_BIN" - "$BUILD_SERVER_CONFIG" "$RUNNER_MANIFEST" "$COMMAND_LABEL" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
command_label = sys.argv[3]

config = json.loads(config_path.read_text())
commands = config.get("commands", {})
if command_label not in commands:
    raise SystemExit(f"unknown command label: {command_label}")

command_spec = commands[command_label]
runner_label = command_spec.get("runner_label", "")
manifest = {}
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text())

runner_spec = manifest.get(runner_label, {}) if runner_label else {}

def normalize_command(value):
    if isinstance(value, list):
        return " ".join(shlex.quote(str(item)) for item in value)
    return "" if value in (None, "") else str(value)

def shell_assign(name, value):
    print(f"{name}={shlex.quote('' if value is None else str(value))}")

image = runner_spec.get("image", command_spec.get("docker_image", ""))
working_dir = runner_spec.get("working_dir", command_spec.get("working_dir", "/workspace"))
timeout_seconds = command_spec.get(
    "timeout_seconds",
    runner_spec.get("timeout_seconds", config.get("default_timeout_seconds", 900)),
)

shell_assign("REMOTE_HOST", config["host"])
shell_assign("SSH_KEY_PATH", os.path.expanduser(config.get("ssh_key", "")))
shell_assign("WORKSPACE_ROOT_BASE", config["workspace_root"])
shell_assign("DEFAULT_TIMEOUT_SECONDS", config.get("default_timeout_seconds", 900))
shell_assign("DOCKER_SOCKET", config.get("docker_socket", ""))
shell_assign("BUILD_SERVER_PIP_CACHE_VOLUME", config.get("pip_cache_volume", ""))
shell_assign("BUILD_SERVER_PACKER_PLUGIN_CACHE", config.get("packer_plugin_cache", ""))
shell_assign("BUILD_SERVER_ANSIBLE_COLLECTION_CACHE", config.get("ansible_collection_cache", ""))
shell_assign("BUILD_SERVER_ANSIBLE_REQUIREMENTS_SHA_FILE", config.get("ansible_requirements_sha_file", ""))
shell_assign("BUILD_SERVER_APT_PROXY_URL", config.get("apt_proxy_url", ""))
shell_assign(
    "SSH_OPTIONS_NL",
    "\n".join(str(item) for item in config.get("ssh_options", [])),
)
shell_assign("REMOTE_COMMAND", command_spec.get("command", normalize_command(runner_spec.get("command"))))
shell_assign("LOCAL_COMMAND", command_spec.get("local_fallback_command", command_spec.get("command", "")))
shell_assign("DOCKER_IMAGE", image)
shell_assign("RUNNER_WORKDIR", working_dir)
shell_assign("TIMEOUT_SECONDS", timeout_seconds)
shell_assign("SKIP_DOCKER", "true" if command_spec.get("skip_docker", False) else "false")
shell_assign("MOUNT_DOCKER_SOCKET", "true" if command_spec.get("mount_docker_socket", False) else "false")
shell_assign("BUILTIN_ACTION", command_spec.get("builtin", ""))
shell_assign(
    "RUNNER_CACHE_MOUNTS_NL",
    "\n".join(str(item) for item in runner_spec.get("cache_mounts", [])),
)
PY
  )"

  [[ -n "$REMOTE_HOST" ]] || fail "remote host is empty in $BUILD_SERVER_CONFIG"
  [[ -n "$WORKSPACE_ROOT_BASE" ]] || fail "workspace_root is empty in $BUILD_SERVER_CONFIG"
  [[ -n "$TIMEOUT_SECONDS" ]] || TIMEOUT_SECONDS="$DEFAULT_TIMEOUT_SECONDS"
}

load_session_workspace() {
  eval "$(
    "$PYTHON_BIN" "$REPO_ROOT/scripts/session_workspace.py" \
      --repo-root "$REPO_ROOT" \
      --remote-workspace-base "$WORKSPACE_ROOT_BASE" \
      --format shell
  )"
  WORKSPACE_ROOT="$LV3_REMOTE_WORKSPACE_ROOT"
  LV3_SESSION_LOCAL_ROOT="$WORKSPACE_ROOT/.local/session-workspaces/$LV3_SESSION_SLUG"
  [[ -n "$WORKSPACE_ROOT" ]] || fail "failed to derive a session-scoped remote workspace path"
}

build_ssh_command() {
  SSH_BASE_CMD=("$SSH_BIN" "-o" "ConnectTimeout=$CONNECT_TIMEOUT" "-o" "BatchMode=yes")
  if [[ -n "$SSH_KEY_PATH" ]]; then
    SSH_BASE_CMD+=("-i" "$SSH_KEY_PATH")
  fi
  if [[ -n "$SSH_OPTIONS_NL" ]]; then
    while IFS= read -r option; do
      [[ -n "$option" ]] || continue
      SSH_BASE_CMD+=("$option")
    done <<< "$SSH_OPTIONS_NL"
  fi
}

worktree_git_checkout() {
  [[ -f "$REPO_ROOT/.git" ]] || return 1
  grep -q '^gitdir:' "$REPO_ROOT/.git"
}

quote_shell() {
  printf "%q" "$1"
}

render_command() {
  local rendered=""
  printf -v rendered "%q " "$@"
  echo "${rendered% }"
}

timeout_prefix() {
  if [[ -n "$TIMEOUT_SECONDS" && "$TIMEOUT_SECONDS" != "0" ]]; then
    printf "timeout --foreground %s " "${TIMEOUT_SECONDS}s"
  fi
}

forwarded_dynamic_env_names() {
  "$PYTHON_BIN" - <<'PY'
import os

prefixes = ("OPENBAO_", "PACKER_", "PKR_VAR_", "PROXMOX_")
for name in sorted(os.environ):
    if any(name.startswith(prefix) for prefix in prefixes):
        print(name)
PY
}

remote_env_exports() {
  local prefix=""
  local name=""
  local dynamic_name=""
  for name in \
    COMMAND \
    IMAGE \
    SERVICE \
    ENV \
    ENVIRONMENT \
    HOST \
    WORKFLOW \
    LV3_SESSION_ID \
    LV3_SESSION_SLUG \
    LV3_SESSION_LOCAL_ROOT \
    LV3_SESSION_NATS_PREFIX \
    LV3_SESSION_STATE_NAMESPACE \
    LV3_SESSION_RECEIPT_SUFFIX \
    LV3_REMOTE_WORKSPACE_ROOT; do
    if [[ -n "${!name:-}" ]]; then
      printf -v prefix "%sexport %s=%q; " "$prefix" "$name" "${!name}"
    fi
  done
  while IFS= read -r dynamic_name; do
    [[ -n "$dynamic_name" ]] || continue
    [[ -n "${!dynamic_name:-}" ]] || continue
    printf -v prefix "%sexport %s=%q; " "$prefix" "$dynamic_name" "${!dynamic_name}"
  done < <(forwarded_dynamic_env_names)
  if [[ -n "$BUILD_SERVER_PACKER_PLUGIN_CACHE" ]]; then
    printf -v prefix "%sexport PACKER_PLUGIN_PATH=%q; " "$prefix" "${BUILD_SERVER_PACKER_PLUGIN_CACHE}/plugins"
  fi
  if [[ -n "$BUILD_SERVER_APT_PROXY_URL" ]]; then
    printf -v prefix "%sexport APT_PROXY_URL=%q; " "$prefix" "$BUILD_SERVER_APT_PROXY_URL"
  fi
  echo "$prefix"
}

remote_docker_env_args() {
  local args=()
  local name=""
  local dynamic_name=""
  for name in \
    COMMAND \
    IMAGE \
    SERVICE \
    ENV \
    ENVIRONMENT \
    HOST \
    WORKFLOW \
    LV3_SESSION_ID \
    LV3_SESSION_SLUG \
    LV3_SESSION_LOCAL_ROOT \
    LV3_SESSION_NATS_PREFIX \
    LV3_SESSION_STATE_NAMESPACE \
    LV3_SESSION_RECEIPT_SUFFIX \
    LV3_REMOTE_WORKSPACE_ROOT; do
    if [[ -n "${!name:-}" ]]; then
      args+=("-e" "$name=${!name}")
    fi
  done
  while IFS= read -r dynamic_name; do
    [[ -n "$dynamic_name" ]] || continue
    [[ -n "${!dynamic_name:-}" ]] || continue
    args+=("-e" "$dynamic_name=${!dynamic_name}")
  done < <(forwarded_dynamic_env_names)
  if [[ -n "$BUILD_SERVER_APT_PROXY_URL" ]]; then
    args+=("-e" "APT_PROXY_URL=$BUILD_SERVER_APT_PROXY_URL")
  fi
  printf "%s\n" "${args[@]}"
}

remote_runner_cache_args() {
  local args=()
  local cache_mount=""

  if [[ -n "$RUNNER_CACHE_MOUNTS_NL" ]]; then
    while IFS= read -r cache_mount; do
      [[ -n "$cache_mount" ]] || continue
      case "$cache_mount" in
        pip)
          [[ -n "$BUILD_SERVER_PIP_CACHE_VOLUME" ]] || continue
          args+=("-v" "${BUILD_SERVER_PIP_CACHE_VOLUME}:/root/.cache/pip" "-e" "PIP_CACHE_DIR=/root/.cache/pip")
          ;;
        packer_plugins)
          [[ -n "$BUILD_SERVER_PACKER_PLUGIN_CACHE" ]] || continue
          args+=("-v" "${BUILD_SERVER_PACKER_PLUGIN_CACHE}:/root/.packer.d")
          ;;
        ansible_collections)
          [[ -n "$BUILD_SERVER_ANSIBLE_COLLECTION_CACHE" ]] || continue
          args+=(
            "-v" "${BUILD_SERVER_ANSIBLE_COLLECTION_CACHE}:${BUILD_SERVER_ANSIBLE_COLLECTION_CACHE}"
            "-e" "LV3_ANSIBLE_COLLECTIONS_DIR=${BUILD_SERVER_ANSIBLE_COLLECTION_CACHE}"
            "-e" "LV3_ANSIBLE_COLLECTIONS_SHA_FILE=${BUILD_SERVER_ANSIBLE_REQUIREMENTS_SHA_FILE}"
            "-e" "ANSIBLE_COLLECTIONS_PATH=${BUILD_SERVER_ANSIBLE_COLLECTION_CACHE}"
            "-e" "ANSIBLE_COLLECTIONS_PATHS=${BUILD_SERVER_ANSIBLE_COLLECTION_CACHE}"
          )
          ;;
      esac
    done <<< "$RUNNER_CACHE_MOUNTS_NL"
  fi

  printf "%s\n" "${args[@]}"
}

remote_reachable() {
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "true" >/dev/null 2>&1
}

sync_remote_gate_status_back() {
  local remote_status=""
  local local_status=""

  case "$COMMAND_LABEL" in
    pre-push-gate|remote-pre-push)
      ;;
    *)
      return 0
      ;;
  esac

  remote_status="$WORKSPACE_ROOT/.local/validation-gate/last-run.json"
  local_status="$REPO_ROOT/.local/validation-gate/last-run.json"
  mkdir -p "$(dirname "$local_status")"

  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "cat $(quote_shell "$remote_status")" > "$local_status" 2>/dev/null || true
}

ensure_remote_workspace() {
  local session_root="$WORKSPACE_ROOT_BASE/.lv3-session-workspaces"
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" \
    "mkdir -p $(quote_shell "$WORKSPACE_ROOT") $(quote_shell "$session_root") && find $(quote_shell "$session_root") -mindepth 1 -maxdepth 1 -type d ! -name $(quote_shell "$LV3_SESSION_SLUG") -mtime +2 -exec rm -rf {} + >/dev/null 2>&1 || true" \
    >/dev/null
}

remote_remove_paths() {
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "rm -rf $* || sudo -n rm -rf $*" >/dev/null
}

prune_remote_workspace_stale_paths() {
  local stale_paths=("$WORKSPACE_ROOT/.git-remote")

  if [[ ! -e "$REPO_ROOT/scripts/cases" ]]; then
    stale_paths+=("$WORKSPACE_ROOT/scripts/cases")
  fi

  remote_remove_paths "$(printf '%q ' "${stale_paths[@]}")"
}

sync_worktree_git_metadata() {
  local ssh_wrapper="$1"
  local remote_git_root="$WORKSPACE_ROOT/.git-remote"
  local worktree_git_dir=""
  local common_git_dir=""
  local worktree_path=""
  local common_path=""
  local worktree_paths=(
    HEAD
    index
    ORIG_HEAD
    logs/HEAD
    config.worktree
  )
  local common_paths=(
    config
    packed-refs
    refs
    info
    shallow
  )

  worktree_git_checkout || return 0

  worktree_git_dir="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-dir)"
  common_git_dir="$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)"

  remote_remove_paths "$(quote_shell "$remote_git_root")"
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" \
    "mkdir -p $(quote_shell "$remote_git_root/worktree") $(quote_shell "$remote_git_root/common")" \
    >/dev/null

  for worktree_path in "${worktree_paths[@]}"; do
    [[ -e "$worktree_git_dir/$worktree_path" ]] || continue
    (
      cd "$worktree_git_dir"
      "$RSYNC_BIN" \
        --archive \
        --relative \
        -e "$ssh_wrapper" \
        "./$worktree_path" \
        "$REMOTE_HOST:$remote_git_root/worktree/"
    ) || return $?
  done

  for common_path in "${common_paths[@]}"; do
    [[ -e "$common_git_dir/$common_path" ]] || continue
    (
      cd "$common_git_dir"
      "$RSYNC_BIN" \
        --archive \
        --relative \
        -e "$ssh_wrapper" \
        "./$common_path" \
        "$REMOTE_HOST:$remote_git_root/common/"
    ) || return $?
  done

  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" \
    "printf '%s\n' '../common' > $(quote_shell "$remote_git_root/worktree/commondir") && printf '%s\n' '../../.git' > $(quote_shell "$remote_git_root/worktree/gitdir") && printf '%s\n' 'gitdir: .git-remote/worktree' > $(quote_shell "$WORKSPACE_ROOT/.git")" \
    >/dev/null
}

sync_workspace() {
  local dry_run="${1:-false}"
  local rc=0
  local ssh_wrapper=""
  local rsync_args=(
    "--archive"
    "--checksum"
    "--delete"
    "--force"
    "--exclude=.git-remote/"
    "--exclude-from=$RSYNC_EXCLUDE_FILE"
  )

  [[ "$dry_run" == "true" ]] && rsync_args+=("--dry-run" "--verbose")

  ssh_wrapper="$(mktemp "${TMPDIR:-/tmp}/remote-exec-ssh.XXXXXX")"
  {
    printf '%s\n' '#!/usr/bin/env bash'
    printf 'exec '
    printf '%q ' "${SSH_BASE_CMD[@]}"
    printf '%s\n' '"$@"'
  } > "$ssh_wrapper"
  chmod 700 "$ssh_wrapper"

  prune_remote_workspace_stale_paths || {
    rm -f "$ssh_wrapper"
    return $?
  }

  "$RSYNC_BIN" \
    "${rsync_args[@]}" \
    -e "$ssh_wrapper" \
    "$REPO_ROOT/" \
    "$REMOTE_HOST:$WORKSPACE_ROOT/" || rc=$?

  if [[ "$rc" -eq 0 ]]; then
    sync_worktree_git_metadata "$ssh_wrapper" || rc=$?
  fi

  rm -f "$ssh_wrapper"
  return "$rc"
}

run_local_command() {
  [[ -n "$LOCAL_COMMAND" ]] || fail "no local fallback command configured for $COMMAND_LABEL"
  echo "remote_exec: running local fallback for $COMMAND_LABEL" >&2
  (
    cd "$REPO_ROOT"
    bash -lc "$LOCAL_COMMAND"
  )
}

run_builtin_check_build_server() {
  echo "Checking SSH connectivity to $REMOTE_HOST"
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "printf 'build-server-ok\n'"

  echo "Checking remote workspace root $WORKSPACE_ROOT_BASE"
  echo "Checking remote session workspace $WORKSPACE_ROOT"
  ensure_remote_workspace
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "cd $(quote_shell "$WORKSPACE_ROOT") && pwd"

  echo "Checking rsync dry-run with excludes from $RSYNC_EXCLUDE_FILE"
  sync_workspace true
}

run_remote_command() {
  local remote_payload=""
  local remote_prefix=""
  local timeout_cmd=""
  local rc=0

  remote_prefix="$(remote_env_exports)"
  timeout_cmd="$(timeout_prefix)"

  if [[ "$BUILTIN_ACTION" == "check-build-server" ]]; then
    run_builtin_check_build_server
    return 0
  fi

  if ! ensure_remote_workspace; then
    if [[ "$LOCAL_FALLBACK" == "true" ]]; then
      echo "remote_exec: remote workspace preparation failed, falling back locally for $COMMAND_LABEL" >&2
      run_local_command
      return $?
    fi
    return 1
  fi

  if ! sync_workspace false; then
    if [[ "$LOCAL_FALLBACK" == "true" ]]; then
      echo "remote_exec: remote sync failed, falling back locally for $COMMAND_LABEL" >&2
      run_local_command
      return $?
    fi
    return 1
  fi

  if [[ "$SKIP_DOCKER" == "true" || -z "$DOCKER_IMAGE" ]]; then
    printf -v remote_payload "cd %q && %sbash -lc %q" \
      "$WORKSPACE_ROOT" \
      "$remote_prefix$timeout_cmd" \
      "$REMOTE_COMMAND"
  else
    local docker_cmd=(
      docker run --rm
      --workdir "$RUNNER_WORKDIR"
      -v "$WORKSPACE_ROOT:$RUNNER_WORKDIR"
    )
    local docker_socket_path=""
    local docker_env_args=()
    local docker_cache_args=()

    mapfile -t docker_env_args < <(remote_docker_env_args)
    mapfile -t docker_cache_args < <(remote_runner_cache_args)
    if [[ -n "$DOCKER_SOCKET" && "$MOUNT_DOCKER_SOCKET" == "true" ]]; then
      docker_socket_path="${DOCKER_SOCKET#unix://}"
      docker_cmd+=("-v" "$docker_socket_path:$docker_socket_path" "-e" "DOCKER_HOST=$DOCKER_SOCKET")
    fi
    if [[ ${#docker_env_args[@]} -gt 0 ]]; then
      docker_cmd+=("${docker_env_args[@]}")
    fi
    if [[ ${#docker_cache_args[@]} -gt 0 ]]; then
      docker_cmd+=("${docker_cache_args[@]}")
    fi
    docker_cmd+=("$DOCKER_IMAGE" "bash" "-lc" "$REMOTE_COMMAND")

    remote_payload="$(timeout_prefix)$(render_command "${docker_cmd[@]}")"
    printf -v remote_payload "cd %q && %s" "$WORKSPACE_ROOT" "$remote_payload"

    if [[ "$VERBOSE" == "1" ]]; then
      echo "Remote docker command: $(render_command "${docker_cmd[@]}")" >&2
    fi
  fi

  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "$remote_payload" || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    sync_remote_gate_status_back
    return 0
  fi
  if [[ "$rc" -ne 0 && "$LOCAL_FALLBACK" == "true" ]]; then
    echo "remote_exec: remote command failed, falling back locally for $COMMAND_LABEL" >&2
    run_local_command
    return $?
  fi
  return "$rc"
}

main() {
  parse_args "$@"
  load_command_configuration
  load_session_workspace
  build_ssh_command

  if remote_reachable; then
    run_remote_command
    return 0
  fi

  if [[ "$LOCAL_FALLBACK" == "true" ]]; then
    run_local_command
    return $?
  fi

  fail "build server $REMOTE_HOST is unreachable; rerun with --local-fallback to execute locally"
}

main "$@"
