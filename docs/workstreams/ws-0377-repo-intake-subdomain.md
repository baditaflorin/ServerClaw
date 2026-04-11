# Workstream WS-0377: Repo Intake As First-Class Subdomain

- ADR: [ADR 0224](../adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md)
- Title: Repo Intake as First-Class Subdomain
- Status: ready
- Branch: `claude/zen-agnesi`
- Worktree: `.claude/worktrees/zen-agnesi`
- Owner: `platform-infrastructure`
- Depends On: `adr-0224-self-service-repo-intake-and-agent-assisted-deployments`
- Conflicts With: none
- Shared Surfaces: `scripts/repo_intake`, `collections/ansible_collections/lv3/platform/roles/repo_intake_runtime`, `playbooks/repo-intake.yml`, `playbooks/services/repo_intake.yml`, `config/generated/nginx-upstreams.yaml`, `inventory/group_vars/platform_services.yml`

## Goal

Extract `repo_intake` from `ops_portal` into a first-class service with its own
published subdomain, mirroring the established ops-portal pattern for
self-service repo deployment workflows.

## Scope

- publish `repo-intake.example.com` as a dedicated platform surface
- keep the runtime isolated from `ops_portal` while preserving the existing
  self-service deployment flow
- update platform navigation surfaces so operators can discover the new entry
  point consistently

## Expected Repo Surfaces

- `scripts/repo_intake`
- `collections/ansible_collections/lv3/platform/roles/repo_intake_runtime`
- `playbooks/repo-intake.yml`
- `playbooks/services/repo_intake.yml`
- `config/generated/nginx-upstreams.yaml`
- `inventory/group_vars/platform_services.yml`
- `workstreams/active/ws-0377-repo-intake-subdomain.yaml`
- `workstreams.yaml`

## Notes

- This workstream extends the ADR 0224 repo-intake lane instead of replacing
  it.
- The active workstream registry and YAML both point at this document; keeping
  it present avoids hidden registry drift during validation and live-apply
  contract checks.
