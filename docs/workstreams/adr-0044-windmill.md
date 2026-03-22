# Workstream ADR 0044: Windmill For Agent And Operator Workflows

- ADR: [ADR 0044](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0044-windmill-for-agent-and-operator-workflows.md)
- Title: On-platform workflow runtime for agents and operators
- Status: merged
- Branch: `codex/adr-0044-windmill`
- Worktree: `../proxmox_florin_server-windmill`
- Owner: codex
- Depends On: `adr-0026-postgres-vm`, `adr-0043-openbao`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `postgres-lv3`, workflow APIs, webhook entry points

## Scope

- choose the workflow runtime for server-side automation
- define how repo-managed scripts become durable scheduled or API-triggered jobs
- constrain how secrets and credentials flow into the runtime

## Non-Goals

- live deployment in this planning workstream
- treating the workflow UI as the source of truth instead of git

## Expected Repo Surfaces

- `docs/adr/0044-windmill-for-agent-and-operator-workflows.md`
- `docs/workstreams/adr-0044-windmill.md`
- `docs/runbooks/plan-agentic-control-plane.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private Windmill deployment on `docker-runtime-lv3`
- database state on `postgres-lv3`
- internal HTTP routes, schedules, and API-triggered jobs

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0044-windmill-for-agent-and-operator-workflows.md`

## Merge Criteria

- the ADR defines Windmill as runtime rather than source of truth
- secret handling and private publication expectations are explicit

## Notes For The Next Assistant

- keep the first rollout private-only
- prefer repo-managed scripts and flows over UI-only definitions
