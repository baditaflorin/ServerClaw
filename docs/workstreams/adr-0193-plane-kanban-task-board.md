# Workstream ADR 0193: Plane Kanban Task Board

- ADR: [ADR 0193](../adr/0193-plane-kanban-task-board.md)
- Title: Deploy a repo-managed Plane task board with authenticated browser access and idempotent ADR synchronization
- Status: blocked
- Branch: `codex/ws-0193-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0193-live-apply`
- Owner: codex
- Depends On: `adr-0096-openbao`, `adr-0146-langfuse`, `adr-0149-semaphore`, `adr-0152-homepage-service-catalog`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/service-completeness.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/service-redundancy-catalog.json`, `config/workflow-catalog.json`, `workstreams.yaml`

## Scope

- add the Plane runtime and PostgreSQL automation
- publish `tasks.lv3.org` through the shared authenticated edge
- expose a controller-facing Tailscale TCP proxy on the Proxmox host
- bootstrap the initial Plane workspace, project, and API token locally
- implement idempotent ADR-to-Plane issue synchronization
- record live-apply verification and merge-to-`main` follow-up notes

## Non-Goals

- rewriting top-level `README.md` integrated truth on this branch
- bumping `VERSION` or cutting release notes on this branch
- updating `versions/stack.yaml` before merge-to-`main`
- claiming native in-app Keycloak OIDC support when the deployed path is edge-auth only

## Expected Repo Surfaces

- `docs/adr/0193-plane-kanban-task-board.md`
- `docs/workstreams/adr-0193-plane-kanban-task-board.md`
- `docs/runbooks/configure-plane.md`
- `playbooks/plane.yml`
- `playbooks/services/plane.yml`
- `roles/plane_postgres/`
- `roles/plane_runtime/`
- `platform/ansible/plane.py`
- `scripts/plane_bootstrap.py`
- `scripts/plane_tool.py`
- `scripts/sync_adrs_to_plane.py`
- `config/*` service-registration updates
- `receipts/live-applies/`

## Expected Live Surfaces

- Plane reachable privately through the Proxmox-host Tailscale proxy
- `tasks.lv3.org` reachable through the shared edge with Keycloak-backed browser auth
- a repo-managed Plane admin, workspace, project, and API token present
- ADR sync able to create or update Plane issues idempotently

## Verification

- `make generate-platform-vars`
- `make syntax-check-plane`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh validate`
- `make live-apply-service service=plane env=production`
- `make plane-manage ACTION=whoami`
- `make plane-manage ACTION=list-projects`
- `python3 scripts/sync_adrs_to_plane.py --auth-file .local/plane/admin-auth.json --adr 0193`

## Merge Criteria

- the repo validators pass from the workstream branch
- the live Plane stack is reachable on both controller and authenticated public paths
- bootstrap artifacts are persisted locally and reused idempotently
- a live-apply receipt captures the applied commit, endpoints, and evidence

## Outcome

- controller/runtime/ADR-sync live apply verified on branch `codex/ws-0193-live-apply`
- `make syntax-check-plane` passed
- `uv run --with pytest pytest -q tests/test_plane_client.py tests/test_plane_runtime_role.py` passed
- `./scripts/validate_repo.sh agent-standards json health-probes workstream-surfaces alert-rules` passed
- `make plane-manage ACTION=whoami` and `make plane-manage ACTION=list-projects PLANE_ARGS='--workspace lv3-platform'` passed after wiring the wrapper to the canonical controller-local auth file
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/plane.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=production -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --tags tier-2 --limit docker-runtime-lv3` passed
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/plane.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=production -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --tags tier-2` reached `postgres-lv3`, `docker-runtime-lv3`, and `nginx-lv3`, then failed on unrelated missing `build/changelog-portal/` and `build/docs-portal/` artifacts in the shared NGINX publication role
- the unscoped full `playbooks/plane.yml` replay is additionally blocked on the externally supplied `HETZNER_DNS_API_TOKEN` required by the shared Hetzner DNS role
- the public `tasks.lv3.org` hostname still returns `308` to `https://nginx.lv3.org/`; merge-to-`main` must not claim the public browser surface is verified until the shared NGINX publication prerequisites and DNS-lane input are available
- merge-to-`main` must still update shared integration truth after the remaining shared-edge blockers are cleared
