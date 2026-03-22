# Workstream ADR 0055: Portainer For Read-Mostly Docker Runtime Operations

- ADR: [ADR 0055](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0055-portainer-for-read-mostly-docker-runtime-operations.md)
- Title: Visual Docker runtime inspection with bounded control actions
- Status: live_applied
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
- `docs/runbooks/configure-portainer.md`
- `playbooks/portainer.yml`
- `roles/portainer_runtime/`
- `scripts/portainer_tool.py`
- `workstreams.yaml`

## Expected Live Surfaces

- a private Docker runtime console on `docker-runtime-lv3`
- Tailscale operator entrypoint at `https://100.118.189.95:9444`
- controller-local Portainer bootstrap artifacts under `.local/portainer/`
- narrowed runtime actions through `make portainer-manage`

## Verification

- `ruby -e 'require "yaml"; YAML.load_file("/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/workstreams.yaml"); puts "workstreams.yaml OK"'`
- `make syntax-check-portainer`
- `make converge-portainer`
- `curl -sk https://100.118.189.95:9444/api/system/status`
- `make portainer-manage ACTION=list-containers PORTAINER_ARGS='--all'`
- `make portainer-manage ACTION=container-logs PORTAINER_ARGS='--container portainer --tail 5'`
- `make portainer-manage ACTION=restart-container PORTAINER_ARGS='--container portainer'`

## Merge Criteria

- the ADR is explicit about read-mostly use and drift handling
- the repo-managed Portainer converge path applies cleanly from `main`
- private access, controller-local bootstrap artifacts, and governed runtime actions are verified live

## Notes For The Next Assistant

- treat UI-authored stack changes as an exception path, not normal delivery
- Portainer surfaced pre-existing unmanaged containers on docker-runtime-lv3 during rollout; leave those visible for inspection, but do not normalize them into repo truth without a separate ADR or integration step
