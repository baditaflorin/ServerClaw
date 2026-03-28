#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTION_ROLES_ROOT="collections/ansible_collections/lv3/platform/roles"

role_paths_from_files() {
  awk -F/ '
    $1 == "collections" && $2 == "ansible_collections" && $3 == "lv3" && $4 == "platform" && $5 == "roles" && $6 != "" {
      print $1 "/" $2 "/" $3 "/" $4 "/" $5 "/" $6
    }
  '
}

base_ref() {
  if git -C "$REPO_ROOT" rev-parse --verify --quiet origin/main >/dev/null 2>/dev/null; then
    git -C "$REPO_ROOT" merge-base HEAD origin/main 2>/dev/null || git -C "$REPO_ROOT" rev-parse HEAD
  else
    git -C "$REPO_ROOT" rev-parse HEAD
  fi
}

collect_candidate_roles() {
  local base
  base="$(base_ref)"
  local changed_from_base=""

  if ! changed_from_base="$(git -C "$REPO_ROOT" diff --name-only "$base"...HEAD -- "$COLLECTION_ROLES_ROOT" 2>/dev/null)"; then
    changed_from_base=""
  fi

  {
    printf '%s\n' "$changed_from_base"
    git -C "$REPO_ROOT" diff --name-only --cached -- "$COLLECTION_ROLES_ROOT"
    git -C "$REPO_ROOT" diff --name-only -- "$COLLECTION_ROLES_ROOT"
    git -C "$REPO_ROOT" ls-files --others --exclude-standard -- "$COLLECTION_ROLES_ROOT"
  } | role_paths_from_files | awk '!seen[$0]++'
}

main() {
  local missing=0
  local role_dir
  local changed_roles=()
  local line

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    changed_roles+=("$line")
  done < <(collect_candidate_roles)

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
      echo "Missing meta/argument_specs.yml for ${role_dir#"$COLLECTION_ROLES_ROOT"/}" >&2
      missing=1
    fi
  done

  if [[ $missing -ne 0 ]]; then
    exit 1
  fi
}

main "$@"
