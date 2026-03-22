#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATION_CACHE_DIR="$REPO_ROOT/.ansible/validation"
ANSIBLE_COLLECTIONS_DIR="$VALIDATION_CACHE_DIR/collections"
ANSIBLE_PLAYBOOK_CMD=(uvx --from ansible-core ansible-playbook)
ANSIBLE_GALAXY_CMD=(uvx --from ansible-core ansible-galaxy)
ANSIBLE_LINT_CMD=(uvx --from ansible-lint ansible-lint)
YAMLLINT_CMD=(uvx --from yamllint yamllint)

export ANSIBLE_CONFIG="$REPO_ROOT/ansible.cfg"
export ANSIBLE_COLLECTIONS_PATH="$ANSIBLE_COLLECTIONS_DIR"

usage() {
  cat <<'EOF'
Usage:
  scripts/validate_repo.sh [all|generated-vars|ansible-syntax|yaml|ansible-lint|shell|json|data-models|generated-docs]...

Examples:
  scripts/validate_repo.sh
  scripts/validate_repo.sh ansible-syntax ansible-lint
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
  mkdir -p "$ANSIBLE_COLLECTIONS_DIR"
  "${ANSIBLE_GALAXY_CMD[@]}" collection install \
    -r "$REPO_ROOT/collections/requirements.yml" \
    -p "$ANSIBLE_COLLECTIONS_DIR" \
    >/dev/null
}

validate_ansible_syntax() {
  local playbook
  local playbooks=()

  install_collections
  mapfile -t playbooks < <(tracked_files 'playbooks/*.yml')
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
    tracked_files 'playbooks/*.yml' 'roles/*/*' |
      awk -F/ '
        $1 == "playbooks" && $NF ~ /\.yml$/ { print; next }
        $1 == "roles" && $2 != "" { print $1 "/" $2 }
      ' |
      awk '!seen[$0]++'
  )
  if [[ ${#lint_targets[@]} -eq 0 ]]; then
    return 0
  fi
  (
    cd "$REPO_ROOT"
    "${ANSIBLE_LINT_CMD[@]}" "${lint_targets[@]}"
  )
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

validate_data_models() {
  echo "Repository data model validation"
  uvx --from pyyaml python "$REPO_ROOT/scripts/validate_repository_data_models.py" --validate >/dev/null
}

validate_generated_docs() {
  echo "Generated status document validation"
  uvx --from pyyaml python "$REPO_ROOT/scripts/generate_status_docs.py" --check >/dev/null
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
      validate_ansible_lint
      validate_shell
      validate_json
      validate_data_models
      validate_generated_docs
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
    ansible-lint)
      validate_ansible_lint
      ;;
    shell)
      validate_shell
      ;;
    json)
      validate_json
      ;;
    data-models)
      validate_data_models
      ;;
    generated-docs)
      validate_generated_docs
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
