#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATION_CACHE_DIR="${LV3_VALIDATION_CACHE_DIR:-$REPO_ROOT/.ansible/validation}"
ANSIBLE_COLLECTIONS_DIR="${LV3_ANSIBLE_COLLECTIONS_DIR:-$VALIDATION_CACHE_DIR/collections}"
ANSIBLE_COLLECTIONS_SHA_FILE="${LV3_ANSIBLE_COLLECTIONS_SHA_FILE:-$VALIDATION_CACHE_DIR/requirements.sha}"
ANSIBLE_PLAYBOOK_CMD=(uvx --from ansible-core ansible-playbook)
ANSIBLE_GALAXY_CMD=(uvx --from ansible-core ansible-galaxy)
ANSIBLE_LINT_CMD=(uvx --from ansible-lint ansible-lint)
YAMLLINT_CMD=(uvx --from yamllint yamllint)

export ANSIBLE_CONFIG="$REPO_ROOT/ansible.cfg"
export ANSIBLE_COLLECTIONS_PATH="$REPO_ROOT/collections:$ANSIBLE_COLLECTIONS_DIR"

usage() {
  cat <<'EOF'
Usage:
  scripts/validate_repo.sh [all|generated-vars|ansible-syntax|yaml|role-argument-specs|ansible-lint|shell|json|compose-runtime-envs|data-models|generated-docs|generated-portals|health-probes|alert-rules|tofu]...

Examples:
  scripts/validate_repo.sh
  scripts/validate_repo.sh ansible-syntax role-argument-specs ansible-lint
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

tracked_files() {
  git -C "$REPO_ROOT" ls-files -- "$@"
}

install_collections() {
  local requirements_file="$REPO_ROOT/collections/requirements.yml"
  local current_sha_file=""

  [[ -f "$requirements_file" ]] || return 0

  mkdir -p "$ANSIBLE_COLLECTIONS_DIR"
  mkdir -p "$(dirname "$ANSIBLE_COLLECTIONS_SHA_FILE")"

  current_sha_file="$(mktemp)"
  sha256sum "$requirements_file" > "$current_sha_file"
  if [[ -s "$ANSIBLE_COLLECTIONS_SHA_FILE" ]] && find "$ANSIBLE_COLLECTIONS_DIR" -mindepth 1 -print -quit | grep -q .; then
    if cmp -s "$current_sha_file" "$ANSIBLE_COLLECTIONS_SHA_FILE"; then
      rm -f "$current_sha_file"
      return 0
    fi
  fi

  "${ANSIBLE_GALAXY_CMD[@]}" collection install \
    -r "$requirements_file" \
    -p "$ANSIBLE_COLLECTIONS_DIR" \
    >/dev/null
  cp "$current_sha_file" "$ANSIBLE_COLLECTIONS_SHA_FILE"
  rm -f "$current_sha_file"
}

validate_ansible_syntax() {
  local playbook
  local playbooks=()

  install_collections
  mapfile -t playbooks < <(
    tracked_files 'playbooks/*.yml' 'playbooks/groups/*.yml' 'playbooks/services/*.yml' |
      awk -F/ '$1 == "playbooks" && $2 != "tasks" { print }'
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
  uvx --from pyyaml python "$REPO_ROOT/scripts/generate_platform_vars.py" --check >/dev/null
}

validate_yaml() {
  local yaml_files=()

  echo "YAML lint"
  mapfile -t yaml_files < <(tracked_files '*.yml' '*.yaml')
  if [[ ${#yaml_files[@]} -eq 0 ]]; then
    return 0
  fi
  (
    cd "$REPO_ROOT"
    "${YAMLLINT_CMD[@]}" -c .yamllint "${yaml_files[@]}"
  )
}

validate_ansible_lint() {
  local lint_targets=()

  echo "Ansible lint"
  install_collections
  mapfile -t lint_targets < <(
    tracked_files 'playbooks/*.yml' 'playbooks/groups/*.yml' 'playbooks/services/*.yml' |
      awk -F/ '
        $1 == "playbooks" && $2 != "tasks" && $NF ~ /\.yml$/ { print }
      ' |
      awk '!seen[$0]++'
  )
  lint_targets+=("collections/ansible_collections/lv3/platform")
  if [[ ${#lint_targets[@]} -eq 0 ]]; then
    return 0
  fi
  (
    cd "$REPO_ROOT"
    "${ANSIBLE_LINT_CMD[@]}" "${lint_targets[@]}"
  )
}

validate_role_argument_specs() {
  "$REPO_ROOT/scripts/check_role_argument_specs.sh"
}

validate_shell() {
  local shell_files=()

  echo "Shell lint"
  require_command shellcheck
  mapfile -t shell_files < <(tracked_files 'scripts/*.sh')
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
  local json_files=()

  echo "JSON validation"
  mapfile -t json_files < <(tracked_files '*.json')
  for json_file in "${json_files[@]}"; do
    jq empty "$json_file"
  done
}

validate_compose_runtime_envs() {
  local env_files=()

  echo "Compose runtime env guard"
  mapfile -t env_files < <(
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

validate_data_models() {
  echo "Repository data model validation"
  uv run --with pyyaml --with jsonschema python "$REPO_ROOT/scripts/validate_repository_data_models.py" --validate >/dev/null
  uvx --from pyyaml python "$REPO_ROOT/scripts/operator_manager.py" validate >/dev/null
  uv run --with pyyaml --with jsonschema python "$REPO_ROOT/scripts/data_catalog.py" --validate >/dev/null
  uv run --with jsonschema python "$REPO_ROOT/scripts/validate_dependency_graph.py" >/dev/null
  uv run --with pyyaml --with jsonschema python "$REPO_ROOT/scripts/service_catalog.py" --validate >/dev/null
  uvx --from pyyaml python "$REPO_ROOT/scripts/environment_topology.py" --validate >/dev/null
  uvx --from pyyaml python "$REPO_ROOT/scripts/subdomain_catalog.py" --validate >/dev/null
  uvx --from pyyaml python "$REPO_ROOT/scripts/subdomain_exposure_audit.py" --validate >/dev/null
  uv run --with pyyaml python "$REPO_ROOT/scripts/validate_nats_topics.py" --validate >/dev/null
  python3 "$REPO_ROOT/scripts/validate_service_completeness.py" --validate >/dev/null
  "$REPO_ROOT/scripts/agent_tool_registry.py" --export-mcp >/dev/null
  python3 "$REPO_ROOT/scripts/mutation_audit.py" --validate-schema >/dev/null
}

validate_generated_docs() {
  echo "Generated status document validation"
  uvx --from pyyaml python "$REPO_ROOT/scripts/generate_status_docs.py" --check >/dev/null
  uv run --with jsonschema python "$REPO_ROOT/scripts/generate_dependency_diagram.py" --check >/dev/null
}

validate_generated_portals() {
  echo "Generated portal validation"
  uv run --with pyyaml --with jsonschema python "$REPO_ROOT/scripts/generate_ops_portal.py" --check >/dev/null
  uv run --with pyyaml --with jsonschema python "$REPO_ROOT/scripts/generate_changelog_portal.py" --check >/dev/null
  make -C "$REPO_ROOT" docs >/dev/null
}

validate_health_probes() {
  local role
  local roles=(
    alertmanager_runtime
    docker_runtime
    postgres_vm
    monitoring_vm
    backup_vm
    step_ca_runtime
    openbao_runtime
    windmill_runtime
    mattermost_runtime
    mail_platform_runtime
    nginx_edge_publication
    ntfy_runtime
    uptime_kuma_runtime
    netbox_runtime
    open_webui_runtime
    portainer_runtime
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
  uv run --with pyyaml python "$REPO_ROOT/scripts/generate_slo_rules.py" --check >/dev/null
  uv run --with pyyaml python "$REPO_ROOT/scripts/validate_alert_rules.py"
}

validate_tofu() {
  if [[ -d "$REPO_ROOT/tofu" ]]; then
    echo "OpenTofu validation"
    "$REPO_ROOT/scripts/tofu_exec.sh" validate all >/dev/null
  fi
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
      validate_shell
      validate_json
      validate_compose_runtime_envs
      validate_health_probes
      validate_alert_rules
      validate_tofu
      validate_data_models
      validate_generated_docs
      validate_generated_portals
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
    shell)
      validate_shell
      ;;
    json)
      validate_json
      ;;
    compose-runtime-envs)
      validate_compose_runtime_envs
      ;;
    data-models)
      validate_data_models
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
