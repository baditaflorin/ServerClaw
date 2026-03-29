#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_SERVER_CONFIG="${REMOTE_EXEC_CONFIG:-$REPO_ROOT/config/build-server.json}"
RUNNER_MANIFEST="${REMOTE_EXEC_RUNNER_MANIFEST:-$REPO_ROOT/config/check-runner-manifest.json}"
RSYNC_EXCLUDE_FILE="${REMOTE_EXEC_EXCLUDE_FILE:-$REPO_ROOT/.rsync-exclude}"
SSH_BIN="${REMOTE_EXEC_SSH_BIN:-ssh}"
RSYNC_BIN="${REMOTE_EXEC_RSYNC_BIN:-rsync}"
PYTHON_BIN="${REMOTE_EXEC_PYTHON_BIN:-python3}"
TAILSCALE_BIN="${REMOTE_EXEC_TAILSCALE_BIN:-/Applications/Tailscale.app/Contents/MacOS/Tailscale}"
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
RUNNER_ID=""
LOCAL_FALLBACK_RUNNER_ID=""
STATUS_FILE=""
LV3_RUN_ID="${LV3_RUN_ID:-}"
LV3_SESSION_ID="${LV3_SESSION_ID:-}"
LV3_SESSION_SLUG="${LV3_SESSION_SLUG:-}"
LV3_SESSION_LOCAL_ROOT="${LV3_SESSION_LOCAL_ROOT:-}"
LV3_SESSION_NATS_PREFIX="${LV3_SESSION_NATS_PREFIX:-}"
LV3_SESSION_STATE_NAMESPACE="${LV3_SESSION_STATE_NAMESPACE:-}"
LV3_SESSION_RECEIPT_SUFFIX="${LV3_SESSION_RECEIPT_SUFFIX:-}"
LV3_REMOTE_WORKSPACE_ROOT="${LV3_REMOTE_WORKSPACE_ROOT:-}"
LV3_VALIDATION_RUNNER_ID="${LV3_VALIDATION_RUNNER_ID:-}"
RUN_WORKSPACE_ROOT=""
REMOTE_SNAPSHOT_ARCHIVE=""
REMOTE_RUN_ROOT=""
SNAPSHOT_BUILD_DIR=""
LV3_VALIDATION_BASE_REF="${LV3_VALIDATION_BASE_REF:-}"
LV3_VALIDATION_CHANGED_FILES_JSON="${LV3_VALIDATION_CHANGED_FILES_JSON:-}"

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
shell_assign("RUNNER_ID", command_spec.get("runner_id", ""))
shell_assign("LOCAL_FALLBACK_RUNNER_ID", command_spec.get("local_fallback_runner_id", ""))
shell_assign("STATUS_FILE", command_spec.get("status_file", ""))
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

compute_validation_lane_context() {
  local base_ref=""
  local current_branch=""

  case "$COMMAND_LABEL" in
    pre-push-gate|remote-pre-push|remote-validate)
      ;;
    *)
      return 0
      ;;
  esac

  current_branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ "$current_branch" == "main" || "$current_branch" == "HEAD" || -z "$current_branch" ]]; then
    return 0
  fi

  base_ref="$("$PYTHON_BIN" - "$REPO_ROOT" <<'PY'
import subprocess
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
remote_candidate = "origin/main"
remote_exists = subprocess.run(
    ["git", "-C", str(repo_root), "show-ref", "--verify", "--quiet", f"refs/remotes/{remote_candidate}"],
    check=False,
)
print(remote_candidate if remote_exists.returncode == 0 else "main")
PY
)"

  LV3_VALIDATION_BASE_REF="$base_ref"
  LV3_VALIDATION_CHANGED_FILES_JSON="$("$PYTHON_BIN" - "$REPO_ROOT" "$base_ref" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
base_ref = sys.argv[2]

merge_base = subprocess.run(
    ["git", "-C", str(repo_root), "merge-base", base_ref, "HEAD"],
    check=False,
    capture_output=True,
    text=True,
)
if merge_base.returncode != 0:
    print("[]")
    raise SystemExit(0)

merge_base_sha = merge_base.stdout.strip()
changed: set[str] = set()
commands = (
    ["diff", "--name-only", f"{merge_base_sha}..HEAD"],
    ["diff", "--name-only"],
    ["diff", "--cached", "--name-only"],
    ["ls-files", "--others", "--exclude-standard"],
)
for command in commands:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *command],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        continue
    for line in result.stdout.splitlines():
        normalized = line.strip().replace("\\", "/")
        if normalized:
            changed.add(normalized)

print(json.dumps(sorted(changed)))
PY
)"
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

cleanup_snapshot_build_dir() {
  [[ -n "$SNAPSHOT_BUILD_DIR" ]] || return 0
  rm -rf "$SNAPSHOT_BUILD_DIR"
  SNAPSHOT_BUILD_DIR=""
}

build_snapshot() {
  [[ -n "${LV3_SNAPSHOT_ID:-}" ]] && [[ -n "${LV3_SNAPSHOT_ARCHIVE:-}" ]] && return 0

  SNAPSHOT_BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lv3-repo-snapshot.XXXXXX")"
  eval "$(
    "$PYTHON_BIN" "$REPO_ROOT/scripts/repository_snapshot.py" build \
      --repo-root "$REPO_ROOT" \
      --exclude-file "$RSYNC_EXCLUDE_FILE" \
      --output-dir "$SNAPSHOT_BUILD_DIR" \
      --format shell
  )"

  REMOTE_SNAPSHOT_ARCHIVE="$WORKSPACE_ROOT/.lv3-snapshots/${LV3_SNAPSHOT_ID}.tar.gz"
  REMOTE_RUN_ROOT="$WORKSPACE_ROOT/.lv3-runs/$(date -u +%Y%m%dT%H%M%SZ)-${LV3_SNAPSHOT_ID:0:12}"
  RUN_WORKSPACE_ROOT="$REMOTE_RUN_ROOT/repo"
  export LV3_SNAPSHOT_ID LV3_SNAPSHOT_ARCHIVE LV3_SNAPSHOT_GENERATED_AT \
    LV3_SNAPSHOT_SOURCE_COMMIT LV3_SNAPSHOT_BRANCH LV3_SNAPSHOT_FILE_COUNT

  if [[ "$VERBOSE" == "1" ]]; then
    echo "remote_exec: built immutable snapshot ${LV3_SNAPSHOT_ID} from ${LV3_SNAPSHOT_BRANCH}@${LV3_SNAPSHOT_SOURCE_COMMIT}" >&2
    echo "remote_exec: remote run namespace ${RUN_WORKSPACE_ROOT}" >&2
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
    LV3_RUN_ID \
    LV3_SESSION_ID \
    LV3_SESSION_SLUG \
    LV3_SESSION_LOCAL_ROOT \
    LV3_SESSION_NATS_PREFIX \
    LV3_SESSION_STATE_NAMESPACE \
    LV3_SESSION_RECEIPT_SUFFIX \
    LV3_REMOTE_WORKSPACE_ROOT \
    LV3_VALIDATION_RUNNER_ID \
    LV3_SNAPSHOT_ID \
    LV3_SNAPSHOT_MANIFEST \
    LV3_SNAPSHOT_GENERATED_AT \
    LV3_SNAPSHOT_SOURCE_COMMIT \
    LV3_SNAPSHOT_BRANCH \
    LV3_SNAPSHOT_FILE_COUNT \
    LV3_VALIDATION_BASE_REF \
    LV3_VALIDATION_CHANGED_FILES_JSON; do
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
  local safe_directories=()
  local safe_directory=""
  for name in \
    COMMAND \
    IMAGE \
    SERVICE \
    ENV \
    ENVIRONMENT \
    HOST \
    WORKFLOW \
    LV3_RUN_ID \
    LV3_SESSION_ID \
    LV3_SESSION_SLUG \
    LV3_SESSION_LOCAL_ROOT \
    LV3_SESSION_NATS_PREFIX \
    LV3_SESSION_STATE_NAMESPACE \
    LV3_SESSION_RECEIPT_SUFFIX \
    LV3_REMOTE_WORKSPACE_ROOT \
    LV3_VALIDATION_RUNNER_ID \
    LV3_SNAPSHOT_ID \
    LV3_SNAPSHOT_MANIFEST \
    LV3_SNAPSHOT_GENERATED_AT \
    LV3_SNAPSHOT_SOURCE_COMMIT \
    LV3_SNAPSHOT_BRANCH \
    LV3_SNAPSHOT_FILE_COUNT \
    LV3_VALIDATION_BASE_REF \
    LV3_VALIDATION_CHANGED_FILES_JSON; do
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
  safe_directories=("$RUNNER_WORKDIR")
  if [[ "$RUNNER_WORKDIR" != "/workspace" ]]; then
    safe_directories+=("/workspace")
  fi
  args+=("-e" "GIT_CONFIG_COUNT=${#safe_directories[@]}")
  for name in "${!safe_directories[@]}"; do
    safe_directory="${safe_directories[$name]}"
    args+=("-e" "GIT_CONFIG_KEY_${name}=safe.directory")
    args+=("-e" "GIT_CONFIG_VALUE_${name}=${safe_directory}")
  done
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

mesh_proxy_configured() {
  [[ "$SSH_OPTIONS_NL" =~ 100\.[0-9]+\.[0-9]+\.[0-9]+ ]]
}

local_mesh_diagnostic() {
  local status_output=""

  mesh_proxy_configured || return 0
  [[ -x "$TAILSCALE_BIN" ]] || return 0

  status_output="$("$TAILSCALE_BIN" status 2>&1 || true)"

  if [[ "$status_output" == *"You are logged out"* || "$status_output" == *"unexpected state: NoState"* ]]; then
    printf '%s' "; controller appears logged out of the Headscale/Tailscale mesh"
    return 0
  fi

  if [[ "$status_output" == *"Unable to connect to the Tailscale coordination server"* || "$status_output" == *"fetch control key:"* ]]; then
    printf '%s' "; controller cannot reach the Headscale/Tailscale coordination server"
  fi
}

sync_remote_gate_status_back() {
  local remote_status=""
  local local_status=""
  local status_workspace_root="${RUN_WORKSPACE_ROOT:-$WORKSPACE_ROOT}"

  [[ -n "$STATUS_FILE" ]] || return 0

  remote_status="$status_workspace_root/$STATUS_FILE"
  local_status="$REPO_ROOT/$STATUS_FILE"
  mkdir -p "$(dirname "$local_status")"

  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "cat $(quote_shell "$remote_status")" > "$local_status" 2>/dev/null || true
}

ensure_remote_workspace() {
  local session_root="$WORKSPACE_ROOT_BASE/.lv3-session-workspaces"
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" \
    "mkdir -p $(quote_shell "$WORKSPACE_ROOT") $(quote_shell "$WORKSPACE_ROOT/.lv3-snapshots") $(quote_shell "$WORKSPACE_ROOT/.lv3-runs") $(quote_shell "$session_root") && find $(quote_shell "$session_root") -mindepth 1 -maxdepth 1 -type d ! -name $(quote_shell "$LV3_SESSION_SLUG") -mtime +2 -exec rm -rf {} + >/dev/null 2>&1 || true && find $(quote_shell "$WORKSPACE_ROOT/.lv3-runs") -mindepth 1 -maxdepth 1 -type d -mtime +2 -exec rm -rf {} + >/dev/null 2>&1 || true && find $(quote_shell "$WORKSPACE_ROOT/.lv3-snapshots") -mindepth 1 -maxdepth 1 -type f -mtime +2 -delete >/dev/null 2>&1 || true" \
    >/dev/null
}

remote_remove_paths() {
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" "rm -rf $* || sudo -n rm -rf $*" >/dev/null
}

prepare_remote_run_namespace() {
  local remote_manifest_path="$REMOTE_RUN_ROOT/metadata/manifest.json"
  "${SSH_BASE_CMD[@]}" "$REMOTE_HOST" \
    "rm -rf $(quote_shell "$REMOTE_RUN_ROOT") && mkdir -p $(quote_shell "$REMOTE_RUN_ROOT") && tar -xzf $(quote_shell "$REMOTE_SNAPSHOT_ARCHIVE") -C $(quote_shell "$REMOTE_RUN_ROOT") && test -f $(quote_shell "$remote_manifest_path")" \
    >/dev/null
}

sync_snapshot() {
  local dry_run="${1:-false}"
  local rc=0
  local ssh_wrapper=""
  local rsync_args=(
    "--archive"
    "--checksum"
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

  "$RSYNC_BIN" \
    "${rsync_args[@]}" \
    -e "$ssh_wrapper" \
    "$LV3_SNAPSHOT_ARCHIVE" \
    "$REMOTE_HOST:$REMOTE_SNAPSHOT_ARCHIVE" || rc=$?

  rm -f "$ssh_wrapper"
  return "$rc"
}

run_local_command() {
  [[ -n "$LOCAL_COMMAND" ]] || fail "no local fallback command configured for $COMMAND_LABEL"
  echo "remote_exec: running local fallback for $COMMAND_LABEL" >&2
  (
    cd "$REPO_ROOT"
    if [[ -n "$LOCAL_FALLBACK_RUNNER_ID" ]]; then
      export LV3_VALIDATION_RUNNER_ID="$LOCAL_FALLBACK_RUNNER_ID"
    fi
    if [[ -z "${LV3_VALIDATE_PYTHON_BIN:-}" ]]; then
      export LV3_VALIDATE_PYTHON_BIN
      LV3_VALIDATE_PYTHON_BIN="$(command -v python3 2>/dev/null || true)"
    fi
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

  build_snapshot
  echo "Checking immutable snapshot dry-run upload from $LV3_SNAPSHOT_BRANCH@$LV3_SNAPSHOT_SOURCE_COMMIT"
  sync_snapshot true
}

run_remote_command() {
  local remote_payload=""
  local remote_prefix=""
  local timeout_cmd=""
  local rc=0

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

  build_snapshot

  if ! sync_snapshot false; then
    if [[ "$LOCAL_FALLBACK" == "true" ]]; then
      echo "remote_exec: snapshot upload failed, falling back locally for $COMMAND_LABEL" >&2
      run_local_command
      return $?
    fi
    return 1
  fi

  if ! prepare_remote_run_namespace; then
    if [[ "$LOCAL_FALLBACK" == "true" ]]; then
      echo "remote_exec: remote snapshot unpack failed, falling back locally for $COMMAND_LABEL" >&2
      run_local_command
      return $?
    fi
    return 1
  fi

  LV3_REMOTE_WORKSPACE_ROOT="$RUN_WORKSPACE_ROOT"
  LV3_SESSION_LOCAL_ROOT="$RUN_WORKSPACE_ROOT/.local/session-workspaces/$LV3_SESSION_SLUG"
  export LV3_SNAPSHOT_MANIFEST="$REMOTE_RUN_ROOT/metadata/manifest.json"
  if [[ -n "$RUNNER_ID" ]]; then
    export LV3_VALIDATION_RUNNER_ID="$RUNNER_ID"
  fi

  remote_prefix="$(remote_env_exports)"
  timeout_cmd="$(timeout_prefix)"

  if [[ "$SKIP_DOCKER" == "true" || -z "$DOCKER_IMAGE" ]]; then
    printf -v remote_payload "cd %q && %sbash -lc %q" \
      "$RUN_WORKSPACE_ROOT" \
      "$remote_prefix$timeout_cmd" \
      "$REMOTE_COMMAND"
  else
    local docker_cmd=(
      docker run --rm
      --workdir "$RUNNER_WORKDIR"
      -v "$RUN_WORKSPACE_ROOT:$RUNNER_WORKDIR"
    )
    local docker_socket_path=""
    local docker_env_args=()
    local docker_cache_args=()
    local image_ready_cmd=""

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

    printf -v image_ready_cmd "%sbash -lc %q" \
      "$(timeout_prefix)" \
      "docker image inspect $(quote_shell "$DOCKER_IMAGE") >/dev/null 2>&1 || docker pull $(quote_shell "$DOCKER_IMAGE") >/dev/null"
    remote_payload="$image_ready_cmd && $(render_command "${docker_cmd[@]}")"
    printf -v remote_payload "cd %q && %s" "$RUN_WORKSPACE_ROOT" "$remote_payload"

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
  compute_validation_lane_context
  build_ssh_command
  trap cleanup_snapshot_build_dir EXIT

  if remote_reachable; then
    run_remote_command
    return 0
  fi

  if [[ "$LOCAL_FALLBACK" == "true" ]]; then
    run_local_command
    return $?
  fi

  fail "build server $REMOTE_HOST is unreachable$(local_mesh_diagnostic); rerun with --local-fallback to execute locally"
}

main "$@"
