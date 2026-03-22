#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

role_paths_from_files() {
  awk -F/ '$1 == "roles" && $2 != "" { print $1 "/" $2 }'
}

base_ref() {
  if git -C "$REPO_ROOT" rev-parse --verify --quiet origin/main >/dev/null; then
    git -C "$REPO_ROOT" merge-base HEAD origin/main
  else
    git -C "$REPO_ROOT" rev-parse HEAD
  fi
}

collect_candidate_roles() {
  local base
  base="$(base_ref)"

  {
    git -C "$REPO_ROOT" diff --name-only "$base"...HEAD -- 'roles/*' 'roles/*/*' 'roles/*/*/*'
    git -C "$REPO_ROOT" diff --name-only --cached -- 'roles/*' 'roles/*/*' 'roles/*/*/*'
    git -C "$REPO_ROOT" diff --name-only -- 'roles/*' 'roles/*/*' 'roles/*/*/*'
    git -C "$REPO_ROOT" ls-files --others --exclude-standard -- 'roles/*' 'roles/*/*' 'roles/*/*/*'
  } | role_paths_from_files | awk '!seen[$0]++'
}

main() {
  local missing=0
  local role_dir

  mapfile -t changed_roles < <(collect_candidate_roles)

  if [[ ${#changed_roles[@]} -eq 0 ]]; then
    echo "Role argument specs: no new or changed roles to check"
    return 0
  fi

  echo "Role argument specs"
  for role_dir in "${changed_roles[@]}"; do
    if [[ ! -d "$REPO_ROOT/$role_dir" ]]; then
      continue
    fi
    if [[ ! -f "$REPO_ROOT/$role_dir/meta/argument_specs.yml" ]]; then
      echo "Missing meta/argument_specs.yml for ${role_dir#roles/}" >&2
      missing=1
    fi
  done

  if [[ $missing -ne 0 ]]; then
    exit 1
  fi
}

main "$@"
