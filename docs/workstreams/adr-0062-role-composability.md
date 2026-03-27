# Workstream ADR 0062: Ansible Role Composability And DRY Defaults

- ADR: [ADR 0062](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0062-ansible-role-composability-and-dry-defaults.md)
- Title: Eliminate copy-paste across Ansible roles with a shared task library and argument specs
- Status: merged
- Branch: `codex/adr-0062-role-composability`
- Worktree: `../proxmox_florin_server-role-composability`
- Owner: codex
- Depends On: none
- Conflicts With: any workstream that adds a new role before the template exists
- Shared Surfaces: all roles, `roles/common/`, `filter_plugins/`, `make validate`

## Scope

- create `roles/common/tasks/` with shared task files: `systemd_unit.yml`, `assert_vars.yml`, `wait_port.yml`, `directory_tree.yml`
- create `roles/_template/` as the canonical starting point for new roles
- move duplicated cross-role variables to `inventory/group_vars/all.yml` or `roles/common/defaults/main.yml`
- add `meta/argument_specs.yml` to every new role
- add a `make validate` lint rule that enforces argument spec presence on new roles

## Non-Goals

- backfilling `meta/argument_specs.yml` into all 50+ existing roles in one pass
- shared handler definitions across roles

## Expected Repo Surfaces

- `roles/common/tasks/systemd_unit.yml`
- `roles/common/tasks/assert_vars.yml`
- `roles/common/tasks/wait_port.yml`
- `roles/common/tasks/directory_tree.yml`
- `roles/common/defaults/main.yml`
- `roles/_template/` directory tree
- updated `scripts/validate_repo.sh` lint rule
- `docs/adr/0062-ansible-role-composability-and-dry-defaults.md`
- `docs/workstreams/adr-0062-role-composability.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no live changes; this is a repository-only refactor

## Verification

- `make validate` passes with the new lint rule active
- `test -d /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/common/tasks`
- `test -d /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/_template`

## Merge Criteria

- all new shared task files are idempotent
- at least two existing roles are updated to use a shared task file as a proof-of-concept
- the lint rule is documented in `docs/runbooks/validate-repository-automation.md`

## Notes For The Next Assistant

- implemented as a repo-only refactor with shared task entrypoints under `roles/common/` and a canonical new-role template under `roles/_template/`
- proof-of-concept consumers now include `docker_runtime`, `proxmox_tailscale`, `uptime_kuma_runtime`, and `windmill_runtime`
- `make validate` now includes a role-interface check that requires `meta/argument_specs.yml` on new or changed roles while leaving untouched legacy roles out of scope
