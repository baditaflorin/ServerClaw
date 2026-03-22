# Workstream ADR 0079: Playbook Decomposition And Shared Execution Model

- ADR: [ADR 0079](../adr/0079-playbook-decomposition-and-shared-execution-model.md)
- Title: Restructure playbooks into composable groups with shared preflight, post-verify, and environment-aware host resolution
- Status: ready
- Branch: `codex/adr-0079-playbook-decomposition`
- Worktree: `../proxmox_florin_server-playbook-decomposition`
- Owner: codex
- Depends On: `adr-0062-role-composability`, `adr-0063-platform-vars-library`, `adr-0072-staging-environment`, `adr-0064-health-probe-contracts`, `adr-0066-mutation-audit-log`
- Conflicts With: any workstream that adds a new playbook without the shared preflight import
- Shared Surfaces: `playbooks/`, `Makefile`, all existing playbook files

## Scope

- create `playbooks/tasks/preflight.yml` with: secrets assertion, SSH connectivity check, env validation, audit log start event
- create `playbooks/tasks/post-verify.yml` with: health probe call, play completion audit event
- create `playbooks/tasks/notify.yml` with: NATS event publish, Mattermost notification on completion
- create `playbooks/groups/` directory with six group playbooks (security, observability, automation, data, access, communication)
- add `env` variable resolution to all existing service playbooks via platform facts (ADR 0063)
- add three-tier tagging to all plays (`tier-1`, `tier-2`, `tier-3` + functional tag)
- update `Makefile` with `live-apply-group`, `live-apply-service`, `live-apply-site` targets
- document the new playbook model in `docs/runbooks/playbook-execution-model.md`

## Non-Goals

- backfilling all 17 existing playbooks to use pre_tasks/post_tasks in one pass — priority services first, others in follow-on
- molecule testing for role idempotency (separate hardening workstream)

## Expected Repo Surfaces

- `playbooks/tasks/preflight.yml`
- `playbooks/tasks/post-verify.yml`
- `playbooks/tasks/notify.yml`
- `playbooks/groups/` directory with six group playbooks
- updated service playbooks for the five priority services (grafana, openbao, step-ca, windmill, mail)
- updated `Makefile`
- `docs/runbooks/playbook-execution-model.md`
- `docs/adr/0079-playbook-decomposition-and-shared-execution-model.md`
- `docs/workstreams/adr-0079-playbook-decomposition.md`
- `workstreams.yaml`

## Expected Live Surfaces

- no live changes; this is a repository-only restructuring
- all playbooks must remain idempotent and produce the same live outcome as before restructuring

## Verification

- `make live-apply-group group=observability env=staging` runs grafana, loki, tempo, uptime-kuma plays in sequence without error
- `make live-apply-service service=grafana env=staging` runs only the grafana play
- a missing `env` variable produces a clear preflight error, not a mid-task failure
- `make validate` passes (ansible-lint checks new structure)

## Merge Criteria

- all five priority service playbooks use shared preflight and post-verify
- three group playbooks (security, observability, automation) are functional
- `live-apply-group` and `live-apply-service` targets work correctly
- no existing live-apply receipts are invalidated (same plays, same idempotency)

## Notes For The Next Assistant

- restructure files, do not rename them — keep existing paths like `playbooks/grafana.yml` and add the new `playbooks/services/grafana.yml` as a re-export; this prevents breaking existing `make` targets that reference specific files
- the preflight.yml task must not fail if the audit log is not yet configured (early in the bootstrapping sequence); wrap the audit emit in a `when: audit_log_configured | default(false)` guard
- test the `--tags` flag carefully; Ansible tag inheritance through imports behaves differently from includes
