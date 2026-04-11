# Workstream ADR 0193: Plane Kanban Task Board

- ADR: [ADR 0193](../adr/0193-plane-kanban-task-board.md)
- Title: Deploy a repo-managed Plane task board with authenticated browser access and idempotent ADR synchronization
- Status: merged
- Branch: `codex/ws-0193-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0193-live-apply`
- Owner: codex
- Depends On: `adr-0096-openbao`, `adr-0146-langfuse`, `adr-0149-semaphore`, `adr-0152-homepage-service-catalog`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/subdomain-exposure-registry.json`, `config/service-completeness.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/service-redundancy-catalog.json`, `config/workflow-catalog.json`, `build/platform-manifest.json`, `docs/site-generated/architecture/dependency-graph.md`, `workstreams.yaml`

## Scope

- add the Plane runtime and PostgreSQL automation
- publish `tasks.example.com` through the shared authenticated edge
- expose a controller-facing Tailscale TCP proxy on the Proxmox host
- bootstrap the initial Plane workspace, project, and API token locally
- implement idempotent ADR-to-Plane issue synchronization
- record live-apply verification and merged-main follow-up notes

## Non-Goals

- rewriting service behavior outside the Plane and shared-edge surfaces already verified by this workstream
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
- `tasks.example.com` reachable through the shared edge with Keycloak-backed browser auth
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

- full live apply verified on branch `codex/ws-0193-live-apply`
- `make syntax-check-plane` passed
- `uv run --with pytest pytest -q tests/test_plane_client.py tests/test_plane_runtime_role.py tests/test_nginx_edge_publication_role.py` passed
- `./scripts/validate_repo.sh agent-standards json health-probes workstream-surfaces alert-rules` passed after recording the generated dependency-graph surface in the workstream ownership manifest
- `make plane-manage ACTION=whoami` and `make plane-manage ACTION=list-projects PLANE_ARGS='--workspace lv3-platform'` passed after wiring the wrapper to the canonical controller-local auth file
- `make plane-manage ACTION=sync-adrs` completed against the live Plane project after extending the ADR-sync timeout budget for slow Plane PATCH replies
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/plane.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=production -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --limit nginx-edge` passed after switching the shared edge certificate automation to the repo-managed `webroot` ACME path
- `ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/plane.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e env=production -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` passed end to end across `proxmox-host`, `postgres`, `docker-runtime`, and `nginx-edge`
- `https://tasks.example.com/` now returns `302` to `https://tasks.example.com/oauth2/sign_in?...`, and that sign-in path returns `302` into the shared `sso.example.com` realm flow
- merged-main replay from `codex/ws-0193-main-merge` verified the same service from the latest `origin/main`, including the topology-safe Plane controller defaults added after the initial merge candidate
- `make live-apply-service service=plane env=production ALLOW_IN_PLACE_MUTATION=true` reconverged the host, PostgreSQL, runtime, bootstrap, and ADR-sync lanes from merged main
- the final public replay required regenerating `build/changelog-portal/` and `build/docs-portal/` before `make configure-edge-publication env=production` succeeded on `nginx-edge`
- the current `.local/plane/adr-sync-summary.json` now records 218 synchronized ADR issues in Plane
- the mainline evidence is recorded in `receipts/live-applies/2026-03-28-adr-0193-plane-mainline-live-apply.json`
