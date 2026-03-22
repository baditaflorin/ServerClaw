# Workstream ADR 0055: Portainer For Read-Mostly Docker Runtime Operations

- ADR: [ADR 0055](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0055-portainer-for-read-mostly-docker-runtime-operations.md)
- Title: Visual Docker runtime inspection with bounded control actions
- Status: ready
- Branch: `codex/adr-0055-portainer-operations`
- Worktree: `../proxmox_florin_server-portainer-operations`
- Owner: codex
- Depends On: `adr-0023-docker-runtime`, `adr-0025-docker-compose-stacks`, `adr-0048-command-catalog`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, Compose stacks, container logs, runtime controls

## Scope

- choose a Docker operations console for inspection and narrow actions
- preserve repo-managed desired state
- define what UI actions are allowed and what remains repo-only

## Non-Goals

- replacing Compose files and git as the source of truth
- granting broad ad hoc mutation rights through the UI

## Expected Repo Surfaces

- `docs/adr/0055-portainer-for-read-mostly-docker-runtime-operations.md`
- `docs/workstreams/adr-0055-portainer-operations.md`
- `docs/runbooks/plan-visual-agent-operations.md`
- `workstreams.yaml`

## Expected Live Surfaces

- a private Docker runtime console on `docker-runtime-lv3`
- narrowed runtime actions for approved operators and agents

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `test -f /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0055-portainer-for-read-mostly-docker-runtime-operations.md`

## Merge Criteria

- the ADR is explicit about read-mostly use and drift handling
- governed runtime actions are described concretely

## Notes For The Next Assistant

- treat UI-authored stack changes as an exception path, not normal delivery
