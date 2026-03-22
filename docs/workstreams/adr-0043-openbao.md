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

- live rollout in this planning workstream
- storing secrets in git-managed files

## Expected Repo Surfaces

- `docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md`
- `docs/workstreams/adr-0043-openbao.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private OpenBao deployment on `docker-runtime-lv3`
- scoped auth roles for humans, agents, and services
- secret retrieval and transit APIs for internal automation

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md`

## Merge Criteria

- the ADR defines OpenBao responsibilities and boundaries clearly
- the workstream leaves a clear path for future implementation and recovery planning

## Notes For The Next Assistant

- keep OpenBao private-only
- do not let it become a second default certificate authority without an explicit follow-up decision
