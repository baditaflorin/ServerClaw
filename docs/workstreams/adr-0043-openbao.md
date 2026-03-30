# Workstream ADR 0043: OpenBao For Secrets, Transit, And Dynamic Credentials

- ADR: [ADR 0043](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md)
- Title: Secret authority for applications, services, and agents
- Status: live_applied
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

- `docker-runtime-lv3` runs the managed OpenBao runtime with integrated Raft storage and controller-managed init and unseal
- `postgres-lv3` serves the managed OpenBao database backend for dynamic read-only PostgreSQL credentials
- controller-local `.local/openbao/` artifacts hold the init payload, named operator passwords, and refreshed short-TTL reusable AppRole credentials

## Verification

- `make syntax-check-openbao`
- `make preflight WORKFLOW=converge-openbao`
- `make validate-data-models`
- `make converge-openbao`

## Merge Criteria

- the repo has a coherent OpenBao converge path with documented bootstrap artifacts, auth boundaries, and PostgreSQL integration
- the live platform proves scoped secret reads, Transit operations, and OpenBao-issued PostgreSQL credentials end to end

## Notes For The Next Assistant

- keep OpenBao private-only
- do not let it become a second default certificate authority without an explicit follow-up decision
- treat `.local/openbao/` as recovery material because it contains the init payload, named-user passwords, and refreshed AppRole credentials
