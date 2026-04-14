#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATION_CACHE_DIR="${LV3_VALIDATION_CACHE_DIR:-$REPO_ROOT/.ansible/validation}"
ANSIBLE_COLLECTIONS_DIR="${LV3_ANSIBLE_COLLECTIONS_DIR:-$VALIDATION_CACHE_DIR/collections}"
ANSIBLE_COLLECTIONS_SHA_FILE="${LV3_ANSIBLE_COLLECTIONS_SHA_FILE:-$VALIDATION_CACHE_DIR/requirements.sha}"
PYTHON_BIN="${LV3_VALIDATE_PYTHON_BIN:-}"
VALIDATION_GALAXY_SERVER="${LV3_VALIDATION_GALAXY_SERVER:-${LV3_ANSIBLE_GALAXY_SERVER:-release_galaxy}}"
UV_CMD=(uv)
ANSIBLE_PLAYBOOK_CMD=()
ANSIBLE_GALAXY_CMD=()
ANSIBLE_LINT_CMD=()
YAMLLINT_CMD=()
HAS_UV=true

export ANSIBLE_CONFIG="$REPO_ROOT/ansible.cfg"
export ANSIBLE_COLLECTIONS_PATH="$REPO_ROOT/collections:$ANSIBLE_COLLECTIONS_DIR"

usage() {
  cat <<'EOF'
Usage:
  scripts/validate_repo.sh [all|generated-vars|ansible-syntax|yaml|role-argument-specs|ansible-lint|ansible-idempotency|shell|json|semgrep|compose-runtime-envs|retry-guard|dependency-direction|service-definitions|data-models|cross-catalog|python-type-safety|waiver-escalation-proofs|policy|architecture-fitness|workstream-surfaces|generated-docs|generated-portals|health-probes|alert-rules|tofu|agent-standards]...

Examples:
  scripts/validate_repo.sh
  scripts/validate_repo.sh ansible-syntax role-argument-specs ansible-lint ansible-idempotency
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

python_candidate_path() {
  local candidate="$1"

  if [[ "$candidate" == */* ]]; then
    [[ -x "$candidate" ]] || return 1
    printf '%s\n' "$candidate"
    return 0
  fi

  command -v "$candidate" 2>/dev/null
}

python_meets_min_version() {
  local candidate="$1"

  "$candidate" - <<'PY' >/dev/null 2>&1
import sys

raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

resolve_python_bin() {
  local candidate=""
  local candidate_path=""
  local candidates=()

  if [[ -n "$PYTHON_BIN" ]]; then
    candidate_path="$(python_candidate_path "$PYTHON_BIN")" || {
      echo "Configured LV3_VALIDATE_PYTHON_BIN is not executable: $PYTHON_BIN" >&2
      exit 1
    }
    python_meets_min_version "$candidate_path" || {
      echo "LV3_VALIDATE_PYTHON_BIN must resolve to Python 3.10 or newer: $candidate_path" >&2
      exit 1
    }
    PYTHON_BIN="$candidate_path"
    return 0
  fi

  candidates=(
    python3
    python3.13
    python3.12
    python3.11
    python3.10
    /opt/homebrew/bin/python3
    /usr/local/bin/python3
  )

  for candidate in "${candidates[@]}"; do
    candidate_path="$(python_candidate_path "$candidate")" || continue
    if python_meets_min_version "$candidate_path"; then
      PYTHON_BIN="$candidate_path"
      return 0
    fi
  done

  echo "Missing Python 3.10+ for validation. Set LV3_VALIDATE_PYTHON_BIN to a compatible interpreter." >&2
  exit 1
}

ensure_uv() {
  resolve_python_bin
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi

  HAS_UV=false
  UV_CMD=()
}

configure_validation_commands() {
  ensure_uv
  if [[ "$HAS_UV" == true ]]; then
    ANSIBLE_PLAYBOOK_CMD=("${UV_CMD[@]}" tool run --from ansible-core ansible-playbook)
    ANSIBLE_GALAXY_CMD=("${UV_CMD[@]}" tool run --from ansible-core ansible-galaxy)
    ANSIBLE_LINT_CMD=("${UV_CMD[@]}" tool run --from ansible-lint ansible-lint)
    YAMLLINT_CMD=("${UV_CMD[@]}" tool run --from yamllint yamllint)
    return 0
  fi

  require_command ansible-playbook
  require_command ansible-galaxy
  require_command ansible-lint
  require_command yamllint
  ANSIBLE_PLAYBOOK_CMD=(ansible-playbook)
  ANSIBLE_GALAXY_CMD=(ansible-galaxy)
  ANSIBLE_LINT_CMD=(ansible-lint)
  YAMLLINT_CMD=(yamllint)
}

ensure_validation_commands_configured() {
  if [[ ${#ANSIBLE_PLAYBOOK_CMD[@]} -eq 0 || ${#ANSIBLE_GALAXY_CMD[@]} -eq 0 || ${#ANSIBLE_LINT_CMD[@]} -eq 0 || ${#YAMLLINT_CMD[@]} -eq 0 ]]; then
    configure_validation_commands
  fi
}

run_uv_python() {
  local packages=()

  resolve_python_bin

  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--" ]]; then
      shift
      break
    fi
    packages+=("$1")
    shift
  done

  "$REPO_ROOT/scripts/run_python_with_packages.sh" "${packages[@]}" -- "$@"
}

run_python_with_requirements() {
  local requirements_file="$1"
  shift

  resolve_python_bin
  ensure_uv
  if [[ "$HAS_UV" == true ]]; then
    "${UV_CMD[@]}" run --with-requirements "$requirements_file" python3 "$@"
    return 0
  fi

  local pip_args=(
    -m
    pip
    install
    --quiet
    --disable-pip-version-check
    -r
    "$requirements_file"
  )
  if "$PYTHON_BIN" -m pip --help 2>/dev/null | grep -q -- "--break-system-packages"; then
    pip_args=( -m pip install --quiet --disable-pip-version-check --break-system-packages -r "$requirements_file" )
  fi
  "$PYTHON_BIN" "${pip_args[@]}"
  "$PYTHON_BIN" "$@"
}

tracked_files() {
  if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$REPO_ROOT" ls-files -- "$@"
    return 0
  fi

  "$PYTHON_BIN" - "$REPO_ROOT" "$@" <<'PY'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1])
patterns = sys.argv[2:]
skip_dirs = {".ansible", ".git", ".local", ".pytest_cache", ".venv", ".worktrees"}
seen: set[str] = set()

for pattern in patterns:
    iterator = repo_root.glob(pattern) if "/" in pattern else repo_root.rglob(pattern)
    for path in sorted(iterator):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        parts = rel.parts
        if any(part in skip_dirs for part in parts[:-1]):
            continue
        if any(part.startswith("._") for part in parts):
            continue
        if rel.name == ".DS_Store":
            continue
        rel_posix = rel.as_posix()
        if rel_posix in seen:
            continue
        seen.add(rel_posix)
        print(rel_posix)
PY
}

load_lines_into_array() {
  local target_name="$1"
  local line=""
  local quoted=""

  eval "$target_name=()"
  while IFS= read -r line; do
    printf -v quoted '%q' "$line"
    eval "$target_name+=( $quoted )"
  done
}

install_collections() {
  local requirements_file="$REPO_ROOT/collections/requirements.yml"
  local current_sha_file=""
  local lock_file="${ANSIBLE_COLLECTIONS_SHA_FILE}.lock"
  local lock_fd=""
  local install_cmd=()

  [[ -f "$requirements_file" ]] || return 0
  ensure_validation_commands_configured

  mkdir -p "$ANSIBLE_COLLECTIONS_DIR"
  mkdir -p "$(dirname "$ANSIBLE_COLLECTIONS_SHA_FILE")"
  mkdir -p "$(dirname "$lock_file")"

  if command -v flock >/dev/null 2>&1; then
    exec {lock_fd}> "$lock_file"
    flock "$lock_fd"
  fi

  current_sha_file="$(mktemp)"
  sha256sum "$requirements_file" > "$current_sha_file"
  if [[ -s "$ANSIBLE_COLLECTIONS_SHA_FILE" ]] && find "$ANSIBLE_COLLECTIONS_DIR" -mindepth 1 -print -quit | grep -q .; then
    if cmp -s "$current_sha_file" "$ANSIBLE_COLLECTIONS_SHA_FILE"; then
      if "$REPO_ROOT/scripts/run_python_with_packages.sh" pyyaml -- - "$requirements_file" "$ANSIBLE_COLLECTIONS_DIR" <<'PY'
import sys
from pathlib import Path

import yaml

requirements_path = Path(sys.argv[1])
collections_dir = Path(sys.argv[2])
payload = yaml.safe_load(requirements_path.read_text(encoding="utf-8")) or {}
collections = payload.get("collections", [])

for entry in collections:
    if isinstance(entry, str):
        name = entry.strip()
    elif isinstance(entry, dict):
        raw_name = entry.get("name", "")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
    else:
        raise SystemExit(1)
    if not name or "." not in name:
        raise SystemExit(1)
    namespace, collection = name.split(".", 1)
    collection_root = collections_dir / "ansible_collections" / namespace / collection
    if not collection_root.is_dir():
        raise SystemExit(1)
    if not (collection_root / "MANIFEST.json").is_file() and not (collection_root / "galaxy.yml").is_file():
        raise SystemExit(1)
PY
      then
        rm -f "$current_sha_file"
        if [[ -n "$lock_fd" ]]; then
          flock -u "$lock_fd"
          eval "exec ${lock_fd}>&-"
        fi
        return 0
      fi
    fi
  fi

  install_cmd=(
    "${ANSIBLE_GALAXY_CMD[@]}"
    collection
    install
  )
  galaxy_server_args=()
  if [[ -n "${LV3_ANSIBLE_GALAXY_SERVER:-}" ]]; then
    galaxy_server_args=(--server "$LV3_ANSIBLE_GALAXY_SERVER")
  else
    galaxy_server_args=(--server "$VALIDATION_GALAXY_SERVER")
  fi
  install_cmd+=(
    "${galaxy_server_args[@]}"
    -r "$requirements_file"
    -p "$ANSIBLE_COLLECTIONS_DIR"
    --force-with-deps
  )

  "${install_cmd[@]}" >/dev/null
  cp "$current_sha_file" "$ANSIBLE_COLLECTIONS_SHA_FILE"
  rm -f "$current_sha_file"
  if [[ -n "$lock_fd" ]]; then
    flock -u "$lock_fd"
    eval "exec ${lock_fd}>&-"
  fi
}

validate_ansible_syntax() {
  local playbook
  local playbooks=()

  install_collections
  load_lines_into_array playbooks < <(
    tracked_files 'playbooks/*.yml' 'playbooks/groups/*.yml' 'playbooks/services/*.yml' |
      awk -F/ '$1 == "playbooks" && $2 != "tasks" && $2 != "vars" && $NF !~ /^\./ { print }'
  )
  if [[ ${#playbooks[@]} -eq 0 ]]; then
    return 0
  fi

  for playbook in "${playbooks[@]}"; do
    echo "Syntax check: ${playbook#"$REPO_ROOT"/}"
    "${ANSIBLE_PLAYBOOK_CMD[@]}" \
      -i "$REPO_ROOT/inventory/hosts.yml" \
      "$playbook" \
      --syntax-check \
      >/dev/null
  done
}

validate_generated_vars() {
  echo "Generated platform vars validation"
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_platform_vars.py" --check >/dev/null
  # ADR 0374: validate the full cross-cutting manifest surface
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_cross_cutting_artifacts.py" --check
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_dns_declarations.py" --check
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_tls_certs.py" --check
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_sso_clients.py" --check
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_nginx_config.py" --check
}

validate_yaml() {
  local yaml_files=()

  echo "YAML lint"
  load_lines_into_array yaml_files < <(
    tracked_files '*.yml' '*.yaml' |
      awk -F/ '$NF !~ /^\./ { print }'
  )
  if [[ ${#yaml_files[@]} -eq 0 ]]; then
    return 0
  fi
  ensure_validation_commands_configured
  (
    cd "$REPO_ROOT"
    "${YAMLLINT_CMD[@]}" -c .yamllint "${yaml_files[@]}"
  )
}

validate_ansible_lint() {
  local lint_targets=()

  echo "Ansible lint"
  install_collections
  load_lines_into_array lint_targets < <(
    tracked_files 'playbooks/*.yml' 'playbooks/groups/*.yml' 'playbooks/services/*.yml' |
      awk -F/ '
        $1 == "playbooks" && $2 != "tasks" && $2 != "vars" && $NF ~ /\.yml$/ && $NF !~ /^\./ { print }
      ' |
      awk '!seen[$0]++'
  )
  lint_targets+=("collections/ansible_collections/lv3/platform")
  if [[ ${#lint_targets[@]} -eq 0 ]]; then
    return 0
  fi
  (
    cd "$REPO_ROOT"
    ANSIBLE_LINT_NODEPS=1 "${ANSIBLE_LINT_CMD[@]}" --offline "${lint_targets[@]}"
  )
}

validate_ansible_idempotency() {
  echo "Ansible role idempotency policy"
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/ansible_role_idempotency.py"
}

validate_role_argument_specs() {
  "$REPO_ROOT/scripts/check_role_argument_specs.sh"
}

validate_shell() {
  local shell_files=()

  echo "Shell lint"
  require_command shellcheck
  load_lines_into_array shell_files < <(tracked_files 'scripts/*.sh')
  if [[ ${#shell_files[@]} -eq 0 ]]; then
    return 0
  fi
  (
    cd "$REPO_ROOT"
    shellcheck "${shell_files[@]}"
  )
}

validate_json() {
  local json_file
  local resolved_json_file=""
  local json_files=()

  echo "JSON validation"
  resolve_python_bin
  load_lines_into_array json_files < <(tracked_files '*.json')
  for json_file in "${json_files[@]}"; do
    if [[ "$json_file" = /* ]]; then
      resolved_json_file="$json_file"
    else
      resolved_json_file="$REPO_ROOT/$json_file"
    fi
    if [[ ! -f "$resolved_json_file" ]]; then
      continue
    fi
    if command -v jq >/dev/null 2>&1; then
      jq empty "$resolved_json_file"
    else
      "$PYTHON_BIN" - "$resolved_json_file" <<'PY'
import json
import pathlib
import sys

json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
PY
    fi
  done
}

validate_semgrep() {
  local semgrep_args=()

  echo "Semgrep SAST and secret-pattern validation"
  mkdir -p "$REPO_ROOT/.local/validation-gate" "$REPO_ROOT/receipts/sast"
  semgrep_args=(
    --repo-root
    "$REPO_ROOT"
    --output-dir
    "$REPO_ROOT/receipts/sast"
    --summary-file
    "$REPO_ROOT/.local/validation-gate/semgrep-summary.json"
  )
  if [[ -n "${LV3_VALIDATION_BASE_REF:-}" ]]; then
    semgrep_args+=(
      --baseline-ref
      "$LV3_VALIDATION_BASE_REF"
      --emit-mutation-audit
    )
  fi
  "$REPO_ROOT/scripts/semgrep_gate.py" "${semgrep_args[@]}"
}

validate_compose_runtime_envs() {
  local env_files=()

  echo "Compose runtime env guard"
  load_lines_into_array env_files < <(
    find "$REPO_ROOT" \
      \( -path "$REPO_ROOT/.git" \
         -o -path "$REPO_ROOT/.ansible" \
         -o -path "$REPO_ROOT/.claude" \
         -o -path "$REPO_ROOT/.local" \
         -o -path "$REPO_ROOT/.venv" \
         -o -path "$REPO_ROOT/.worktrees" \) -prune \
      -o -type f -name '*.env' -print
  )
  if [[ ${#env_files[@]} -gt 0 ]]; then
    printf 'Unexpected committed or generated .env files inside the repository:\n' >&2
    printf '  %s\n' "${env_files[@]#"$REPO_ROOT"/}" >&2
    exit 1
  fi
}

validate_retry_guard() {
  echo "Retry guard"
  resolve_python_bin
  "$PYTHON_BIN" "$REPO_ROOT/scripts/check_ad_hoc_retry.py" >/dev/null
}

validate_dependency_direction() {
  echo "Dependency direction validation"
  python3 "$REPO_ROOT/scripts/validate_dependency_direction.py" >/dev/null
}

validate_service_definitions() {
  echo "Service definition bundle validation"
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/service_definition_catalog.py" --check >/dev/null
}

validate_data_models() {
  echo "Repository data model validation"
  validate_service_definitions
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/ansible_scope_runner.py" validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validation_lanes.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_timeout_hierarchy.py" >/dev/null
  "$PYTHON_BIN" "$REPO_ROOT/scripts/check_hardcoded_timeouts.py" >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/provider_boundary_catalog.py" --validate >/dev/null
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/validate_repository_data_models.py" --validate >/dev/null
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/capability_contracts.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/execution_lanes.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/operator_manager.py" validate >/dev/null
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/data_catalog.py" --validate >/dev/null
  run_uv_python jsonschema -- "$REPO_ROOT/scripts/validate_dependency_graph.py" >/dev/null
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/service_catalog.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/environment_topology.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/subdomain_catalog.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/subdomain_exposure_audit.py" --validate >/dev/null
  "$PYTHON_BIN" "$REPO_ROOT/scripts/validate_service_completeness.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/agent_tool_registry.py" --export-mcp >/dev/null
  "$PYTHON_BIN" "$REPO_ROOT/scripts/mutation_audit.py" --validate-schema >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/atlas_schema.py" validate --repo-root "$REPO_ROOT" >/dev/null
}

validate_cross_catalog() {
  resolve_python_bin
  echo "Cross-catalog referential integrity validation"
  "$PYTHON_BIN" "$REPO_ROOT/scripts/validate_cross_catalog_integrity.py"
}

validate_waiver_escalation_proofs() {
  echo "Gate bypass waiver escalation: Z3 formal verification"
  uvx --from z3-solver python "$REPO_ROOT/scripts/verify_waiver_escalation.py"
}

validate_python_types() {
  echo "Python type safety validation (pyright + bandit + crosshair)"
  # pyright: type-check the catalog-integrity and proof scripts we own, plus Ansible plugins.
  # Broad scripts/ coverage is a separate cleanup task (pre-existing codebase accumulated ~159 errors).
  uvx --quiet pyright --pythonversion 3.12 \
    "$REPO_ROOT/scripts/validate_cross_catalog_integrity.py" \
    "$REPO_ROOT/scripts/verify_waiver_escalation.py" \
    "$REPO_ROOT/scripts/gate_bypass_waivers.py" \
    "$REPO_ROOT/collections/ansible_collections/lv3/platform/plugins/"
  # bandit: security SAST on new catalog-integrity and proof scripts only.
  # Pre-existing scripts have accumulated findings that are tracked separately;
  # expanding the scope here is a dedicated cleanup task, not a gate blocker.
  uvx --from bandit bandit \
    "$REPO_ROOT/scripts/validate_cross_catalog_integrity.py" \
    "$REPO_ROOT/scripts/verify_waiver_escalation.py" \
    --skip B101,B603,B607 \
    --severity-level medium \
    -q
  # crosshair: symbolic contract verification on validation_toolkit
  uvx --from crosshair-tool crosshair check "$REPO_ROOT/scripts/validation_toolkit.py" \
    --per_path_timeout 10 \
    --analysis_kind PEP316
}

validate_policy() {
  echo "ADR 0230 policy validation"
  python3 "$REPO_ROOT/scripts/policy_checks.py" --validate >/dev/null
}

validate_architecture_fitness() {
  echo "Architecture fitness validation"
  resolve_python_bin
  "$PYTHON_BIN" "$REPO_ROOT/scripts/replaceability_scorecards.py" --validate >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_renovate_contract.py" >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/renovate_stack_digest_guard.py" --base-ref origin/main >/dev/null
}

validate_workstream_surfaces() {
  echo "Workstream surface ownership validation"
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/workstream_surface_ownership.py" --validate-registry >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/workstream_surface_ownership.py" --validate-branch --base-ref origin/main >/dev/null
}

validate_generated_docs() {
  echo "Generated status document validation"
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_discovery_artifacts.py" --check >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/canonical_truth.py" --check >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_release_notes.py" --check-root-summaries >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_status_docs.py" --check >/dev/null
  run_uv_python jsonschema -- "$REPO_ROOT/scripts/generate_dependency_diagram.py" --check >/dev/null
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/generate_diagrams.py" --check >/dev/null
}

validate_generated_portals() {
  local generated_docs_dir=""
  local generated_portal_output_dir=""

  echo "Generated portal validation"
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/generate_ops_portal.py" --check \
    --probe-timeout "${OPS_PORTAL_GATE_PROBE_TIMEOUT:-2}" >/dev/null
  run_uv_python pyyaml jsonschema -- "$REPO_ROOT/scripts/generate_changelog_portal.py" --check >/dev/null
  generated_docs_dir="$(mktemp -d "${TMPDIR:-/tmp}/lv3-docs-site.XXXXXX")"
  generated_portal_output_dir="$(mktemp -d "${TMPDIR:-/tmp}/lv3-docs-portal.XXXXXX")"
  trap 'rm -rf "$generated_docs_dir" "$generated_portal_output_dir"' RETURN
  run_python_with_requirements "$REPO_ROOT/requirements/docs.txt" \
    "$REPO_ROOT/scripts/build_docs_portal.py" --generated-dir "$generated_docs_dir" --output-dir "$generated_portal_output_dir" \
    >/dev/null
}

validate_health_probes() {
  local role
  local roles=(
    alertmanager_runtime
    docker_runtime
    dozzle_runtime
    excalidraw_runtime
    postgres_vm
    monitoring_vm
    backup_vm
    step_ca_runtime
    openbao_runtime
    semaphore_runtime
    plane_runtime
    windmill_runtime
    mattermost_runtime
    matrix_synapse_runtime
    mail_platform_runtime
    mailpit_runtime
    paperless_runtime
    tika_runtime
    tesseract_ocr_runtime
    nginx_edge_publication
    ntfy_runtime
    uptime_kuma_runtime
    netbox_runtime
    portainer_runtime
    vaultwarden_runtime
    proxmox_ntopng
  )

  echo "Health probe contract validation"
  for role in "${roles[@]}"; do
    local verify_file="$REPO_ROOT/roles/$role/tasks/verify.yml"
    local main_file="$REPO_ROOT/roles/$role/tasks/main.yml"

    if [[ ! -f "$verify_file" ]]; then
      echo "Missing verify task file: roles/$role/tasks/verify.yml" >&2
      exit 1
    fi

    if ! grep -Eq 'import_tasks: verify\.yml|include_tasks: verify\.yml' "$main_file"; then
      echo "roles/$role/tasks/main.yml does not import verify.yml" >&2
      exit 1
    fi
  done
}

validate_alert_rules() {
  echo "Alert rule validation"
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_slo_rules.py" --check >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_https_tls_assurance.py" --check >/dev/null
  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_alert_rules.py"
}

validate_tofu() {
  if [[ -d "$REPO_ROOT/tofu" ]]; then
    echo "OpenTofu validation"
    "$REPO_ROOT/scripts/tofu_exec.sh" validate all >/dev/null
  fi
}

# ---------------------------------------------------------------------------
# ADR 0168: Agent standards validation
# ---------------------------------------------------------------------------

validate_agent_standards() {
  echo "Agent standards validation (ADR 0163-0168)"
  local rc=0

  _validate_playbook_metadata
  local meta_rc=$?
  [[ $meta_rc -ne 0 ]] && rc=$meta_rc

  _validate_workstream_entry
  local ws_rc=$?
  [[ $ws_rc -ne 0 ]] && rc=$ws_rc

  run_uv_python pyyaml -- "$REPO_ROOT/scripts/workstream_registry.py" --check >/dev/null
  local ws_registry_rc=$?
  [[ $ws_registry_rc -ne 0 ]] && rc=$ws_registry_rc

  _validate_adr_index_current
  local idx_rc=$?
  [[ $idx_rc -ne 0 ]] && rc=$idx_rc

  # Warnings only — do not fail
  _validate_topology_snapshot_fresh || true

  _validate_windmill_raw_app_lockfiles
  local raw_app_lock_rc=$?
  [[ $raw_app_lock_rc -ne 0 ]] && rc=$raw_app_lock_rc

  run_uv_python pyyaml -- "$REPO_ROOT/scripts/generate_discovery_artifacts.py" --check >/dev/null
  local discovery_rc=$?
  [[ $discovery_rc -ne 0 ]] && rc=$discovery_rc

  run_uv_python pyyaml -- "$REPO_ROOT/scripts/validate_public_entrypoints.py" --check >/dev/null
  local public_repo_rc=$?
  [[ $public_repo_rc -ne 0 ]] && rc=$public_repo_rc

  # Warnings only — do not fail
  _validate_config_registry_updated || true
  _validate_structure_index_updated || true

  return $rc
}

_validate_playbook_metadata() {
  local missing_metadata=()
  local playbook

  while IFS= read -r playbook; do
    [[ -z "$playbook" ]] && continue
    [[ ! -f "$REPO_ROOT/$playbook" ]] && continue
    # Check for metadata header: any line starting with "# Purpose:"
    if ! grep -q "^# Purpose:" "$REPO_ROOT/$playbook" 2>/dev/null; then
      missing_metadata+=("$playbook")
    fi
  done < <(
    git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
    grep -E '^(playbooks|collections/.*roles)/.*\.ya?ml$' || true
  )

  if [[ ${#missing_metadata[@]} -gt 0 ]]; then
    echo "ERROR: Playbooks/roles missing metadata headers (ADR 0165):" >&2
    printf '  - %s\n' "${missing_metadata[@]}" >&2
    echo "  Copy header from: playbooks/.metadata-template.yml" >&2
    echo "  Reference: docs/adr/0165-playbook-role-metadata-standard.md" >&2
    return 1
  fi
  return 0
}

_validate_workstream_entry() {
  local current_branch
  current_branch=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")

  # Skip on main, detached HEAD, or CI environments
  [[ "$current_branch" == "main" ]] && return 0
  [[ "$current_branch" == "HEAD" ]] && return 0
  [[ "${CI:-}" == "true" ]] && return 0

  local workstreams_file="$REPO_ROOT/workstreams.yaml"
  [[ ! -f "$workstreams_file" ]] && return 0

  local entry_count
  entry_count=$(grep -Ec "^[[:space:]]*branch:[[:space:]]*\"?$current_branch\"?[[:space:]]*$" "$workstreams_file" 2>/dev/null || true)
  entry_count="${entry_count:-0}"

  if [[ "$entry_count" -eq 0 ]]; then
    echo "WARNING: Branch '$current_branch' not found in workstreams.yaml (ADR 0167)" >&2
    echo "  Add an entry: docs/adr/0167-agent-handoff-and-context-preservation.md" >&2
    # Warning only — do not block push
  fi
  return 0
}

_validate_adr_index_current() {
  local adr_related_changes index_updated

  adr_related_changes=$(git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
    grep -Ec '^(docs/adr/0[0-9]{3}.*\.md|docs/adr/index/reservations\.yaml|scripts/generate_adr_index\.py)$' || true)
  adr_related_changes="${adr_related_changes:-0}"
  index_updated=$(git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
    grep -Ec '^docs/adr/\.index\.yaml$|^docs/adr/index/(by-range|by-concern|by-status)/.+\.yaml$' || true)
  index_updated="${index_updated:-0}"

  if [[ "$adr_related_changes" -gt 0 ]] && [[ "$index_updated" -eq 0 ]]; then
    if [[ ! -f "$REPO_ROOT/docs/adr/.index.yaml" ]]; then
      echo "ERROR: docs/adr/.index.yaml missing (ADR 0164 / ADR 0325). Generate with:" >&2
      echo "  uv run --with pyyaml python3 scripts/generate_adr_index.py --write" >&2
      return 1
    fi
    echo "WARNING: ADR metadata changed but the generated ADR discovery outputs were not refreshed (ADR 0164 / ADR 0325)" >&2
    echo "  Run: uv run --with pyyaml python3 scripts/generate_adr_index.py --write" >&2
    echo "  Then: git add docs/adr/.index.yaml docs/adr/index/" >&2
  fi
  return 0
}

_validate_topology_snapshot_fresh() {
  local snapshot="$REPO_ROOT/scripts/topology-snapshot.json"
  local inv_dir="$REPO_ROOT/inventory"
  if [[ ! -f "$snapshot" ]]; then
    echo "WARNING: scripts/topology-snapshot.json missing (ADR 0344). Generate with:" >&2
    echo "  python3 scripts/generate_topology_snapshot.py --write" >&2
    return 0
  fi
  # Check if any inventory file is newer than the snapshot
  local newer
  newer=$(find "$inv_dir" -name "*.yml" -newer "$snapshot" 2>/dev/null | head -1)
  if [[ -n "$newer" ]]; then
    echo "WARNING: Inventory changed since topology snapshot was generated (ADR 0344)." >&2
    echo "  Newer file: $newer" >&2
    echo "  Run: python3 scripts/generate_topology_snapshot.py" >&2
    echo "  Then: git add scripts/topology-snapshot.json" >&2
  fi
}

_validate_windmill_raw_app_lockfiles() {
  local package_json
  local missing_lockfiles=()

  while IFS= read -r package_json; do
    [[ -z "$package_json" ]] && continue
    local relative_package="${package_json#"$REPO_ROOT"/}"
    local app_dir
    app_dir=$(dirname "$relative_package")
    if [[ ! -f "$REPO_ROOT/$app_dir/package-lock.json" ]]; then
      missing_lockfiles+=("$app_dir/package-lock.json")
    fi
  done < <(
    find "$REPO_ROOT/config/windmill/apps" -type f -name package.json 2>/dev/null |
    grep '\.raw_app/package\.json$' |
    sort
  )

  if [[ ${#missing_lockfiles[@]} -gt 0 ]]; then
    echo "ERROR: Windmill raw apps with frontend dependencies must commit package-lock.json:" >&2
    printf '  - %s\n' "${missing_lockfiles[@]}" >&2
    echo "  Reference: docs/runbooks/configure-windmill.md" >&2
    return 1
  fi
  return 0
}

_validate_config_registry_updated() {
  local new_config_files registry_updated

  new_config_files=$(git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
    grep -cE '^(config/|inventory/|versions)' || true)
  new_config_files="${new_config_files:-0}"
  registry_updated=$(git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
    grep -c '^\.config-locations\.yaml' || true)
  registry_updated="${registry_updated:-0}"

  if [[ "$new_config_files" -gt 3 ]] && [[ "$registry_updated" -eq 0 ]]; then
    echo "WARNING: Config files changed but .config-locations.yaml not updated (ADR 0166)" >&2
  fi
  return 0
}

_validate_structure_index_updated() {
  local new_dirs structure_updated

  new_dirs=$(
    (
      git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
        grep -oE '^[^/]+/' || true
    ) | sort -u | wc -l | tr -d ' '
  )
  new_dirs=${new_dirs:-0}
  structure_updated=$(git -C "$REPO_ROOT" diff --name-only --cached 2>/dev/null |
    grep -c '^\.repo-structure\.yaml' || true)
  structure_updated=${structure_updated:-0}

  if [[ "$new_dirs" -gt 2 ]] && [[ "$structure_updated" -eq 0 ]]; then
    echo "WARNING: New top-level directories detected but .repo-structure.yaml not updated (ADR 0163)" >&2
  fi
  return 0
}

if [[ $# -eq 0 ]]; then
  set -- all
fi

for stage in "$@"; do
  case "$stage" in
    all)
      validate_generated_vars
      validate_ansible_syntax
      validate_yaml
      validate_role_argument_specs
      validate_ansible_lint
      validate_ansible_idempotency
      validate_shell
      validate_json
      validate_semgrep
      validate_compose_runtime_envs
      validate_retry_guard
      validate_dependency_direction
      validate_health_probes
      validate_alert_rules
      validate_tofu
      validate_data_models
      validate_cross_catalog
      validate_python_types
      validate_waiver_escalation_proofs
      validate_policy
      validate_architecture_fitness
      validate_workstream_surfaces
      validate_generated_docs
      validate_generated_portals
      validate_agent_standards
      ;;
    generated-vars)
      validate_generated_vars
      ;;
    ansible-syntax)
      validate_ansible_syntax
      ;;
    yaml)
      validate_yaml
      ;;
    role-argument-specs)
      validate_role_argument_specs
      ;;
    ansible-lint)
      validate_ansible_lint
      ;;
    ansible-idempotency)
      validate_ansible_idempotency
      ;;
    shell)
      validate_shell
      ;;
    json)
      validate_json
      ;;
    semgrep)
      validate_semgrep
      ;;
    compose-runtime-envs)
      validate_compose_runtime_envs
      ;;
    retry-guard)
      validate_retry_guard
      ;;
    dependency-direction)
      validate_dependency_direction
      ;;
    service-definitions)
      validate_service_definitions
      ;;
    data-models)
      validate_data_models
      ;;
    cross-catalog)
      validate_cross_catalog
      ;;
    python-type-safety)
      validate_python_types
      ;;
    waiver-escalation-proofs)
      validate_waiver_escalation_proofs
      ;;
    policy)
      validate_policy
      ;;
    architecture-fitness)
      validate_architecture_fitness
      ;;
    workstream-surfaces)
      validate_workstream_surfaces
      ;;
    health-probes)
      validate_health_probes
      ;;
    alert-rules)
      validate_alert_rules
      ;;
    tofu)
      validate_tofu
      ;;
    agent-standards)
      validate_agent_standards
      ;;
    generated-docs)
      validate_generated_docs
      ;;
    generated-portals)
      validate_generated_portals
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown validation stage: $stage" >&2
      usage >&2
      exit 1
      ;;
  esac
done
