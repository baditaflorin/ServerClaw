# Workstream ADR 0043: OpenBao For Secrets, Transit, And Dynamic Credentials

- ADR: [ADR 0043](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md)
- Title: Secret authority for applications, services, and agents
- Status: merged
- Branch: `codex/adr-0043-openbao`
- Worktree: `../proxmox_florin_server-openbao`
- Owner: codex
- Depends On: `adr-0023-docker-runtime`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, secret distribution, transit operations

## Scope

- choose the secrets authority and auth model
- define how agents and services receive scoped secrets
- document boundaries between secrets, certificates, and repo-local bootstrap material

## Non-Goals

- storing secrets in git-managed files

## Expected Repo Surfaces

- `docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md`
- `docs/workstreams/adr-0043-openbao.md`
- `docs/runbooks/configure-openbao.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `playbooks/openbao.yml`
- `roles/openbao_runtime/`
- `roles/openbao_postgres_backend/`
- `config/controller-local-secrets.json`
- `config/workflow-catalog.json`
- `workstreams.yaml`

## Expected Live Surfaces

- no direct live apply in this integration step
- a ready-to-run OpenBao converge path for later controlled rollout

## Verification

- `make syntax-check-openbao`
- `make workflow-info WORKFLOW=converge-openbao`
- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`

## Merge Criteria

- the repo has a coherent OpenBao converge path with documented bootstrap artifacts, auth boundaries, and PostgreSQL integration
- the workstream leaves a clear path for future live rollout and recovery planning

## Notes For The Next Assistant

- keep OpenBao private-only
- do not let it become a second default certificate authority without an explicit follow-up decision
- live apply should wait for an explicit recovery review because init payloads and unseal artifacts become critical control-plane state
