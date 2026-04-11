# Workstream ws-0370-live-apply: ADR 0370 Shared Lifecycle Includes

- ADR: [ADR 0370](../adr/0370-service-lifecycle-task-includes.md)
- Title: complete ADR 0370 shared lifecycle adoption and live-apply it from latest `origin/main`
- Status: in_progress
- Included In Repo Version: pending exact-main integration
- Branch-Local Receipt: pending
- Canonical Mainline Receipt: pending
- Implemented On: pending
- Live Applied On: pending
- Live Applied In Platform Version: pending exact-main replay
- Latest Verified Base: `origin/main@86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- Branch: `codex/ws-0370-live-apply`
- Worktree: `.worktrees/ws-0370-live-apply`
- Owner: codex
- Depends On: `ADR 0021`, `ADR 0063`, `ADR 0165`, `ADR 0370`, `ADR 0371`
- Conflicts With: none

## Scope

- finish the remaining runtime-role adoption of ADR 0370's shared lifecycle helpers, especially the underused `docker_compose_converge` path
- verify the repo automation surfaces touched by the migration, including workstream, validation, and receipt tooling
- perform the exact-main live apply and record merge-safe evidence for both the branch-local and integrated-mainline replays

## Non-Goals

- bumping `VERSION`, editing numbered release sections, or rewriting the top-level README status summary before the exact-main integration step
- changing the service-specific runtime semantics beyond what is needed to centralize duplicated lifecycle tasks safely
- introducing hidden operator steps instead of repo-managed validation and live-apply evidence

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/check_local_secrets.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/manage_service_secrets.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_compose_converge.yml`
- `collections/ansible_collections/lv3/platform/roles/*_runtime/tasks/main.yml`
- `docs/adr/0370-service-lifecycle-task-includes.md`
- `docs/adr/implementation-status/adr-0370.yaml`
- `docs/workstreams/ws-0370-live-apply.md`
- `workstreams/active/ws-0370-live-apply.yaml`
- `workstreams.yaml`
- `receipts/live-applies/`

## Verification Plan

- branch-local repo validation for the touched automation and Ansible surfaces
- focused playbook syntax or check-mode replays for representative migrated services
- exact-main live apply from the integrated branch head with durable receipt evidence
- post-apply validation proving the shared helper path did not regress the governed runtime lifecycle

## Merge Criteria

- remaining ADR 0370 migration work is committed and branch-local validation passes
- branch-local evidence clearly distinguishes repo validation from exact-main live-apply evidence
- ADR metadata records final implementation and live-apply dates plus any main-only follow-up that remains
- the integrated `main` replay updates only the canonical truth surfaces that belong to the verified final step
