# Workstream ADR 0143: Gitea for Self-Hosted Git and Webhook-Driven Automation

- ADR: [ADR 0143](../adr/0143-gitea-for-self-hosted-git-and-ci.md)
- Title: Private Gitea on docker-runtime with Keycloak OIDC, a docker-build Actions runner, and repo-managed webhook validation
- Status: merged
- Implemented In Repo Version: 0.165.0
- Implemented In Platform Version: 0.130.15
- Implemented On: 2026-03-26
- Branch: `codex/integration-0143-main-refresh-v2`
- Worktree: `.worktrees/integration-0134-main/.worktrees/integration-0143-main-refresh-v2`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0056-keycloak`, `adr-0082-remote-build-gateway`, `adr-0087-validation-gate`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox-host.yml`, `versions/stack.yaml`, `config/service-capability-catalog.json`, `collections/ansible_collections/lv3/platform/roles/`

## Scope

- deploy private Gitea on `docker-runtime` with a managed PostgreSQL database on `postgres`
- expose `git.example.com` only through the Proxmox-host Tailscale TCP proxy
- provision a Keycloak OIDC client and configure Gitea to accept `lv3-platform-admins`
- bootstrap the `ops` org, the canonical `ops/proxmox-host_server` repository path, and the managed pre-receive hook template
- deploy a stable `act_runner` on `docker-build` for Gitea Actions execution
- add the repo-managed `validate` workflow under `.gitea/workflows/`
- register catalog, health probe, subdomain, image, dependency, and data entries for the new service
- verify repository creation and webhook delivery against the live Gitea instance

## Non-Goals

- migrating every existing clone to the new remote in this same workstream
- replacing GitHub as the sole upstream mirror in one step
- publishing Gitea to the public internet

## Expected Repo Surfaces

- `playbooks/gitea.yml`
- `playbooks/services/gitea.yml`
- `playbooks/groups/automation.yml`
- `collections/ansible_collections/lv3/platform/roles/gitea_postgres/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runner/`
- `docs/runbooks/configure-gitea.md`
- `.gitea/workflows/validate.yml`
- `inventory/host_vars/proxmox-host.yml`
- `scripts/generate_platform_vars.py`
- `config/` catalog entries for `gitea`
- `versions/stack.yaml`
- `workstreams.yaml`

## Expected Live Surfaces

- `http://100.64.0.1:3009` serves the private Gitea instance for `git.example.com`
- the Keycloak login source exists in Gitea and admits the `lv3-platform-admins` group
- `docker-build` appears as an online self-hosted Gitea Actions runner
- a test repository under the `ops` org can receive a push and emit a webhook successfully

## Verification

- `ansible-playbook -i inventory/hosts.yml playbooks/gitea.yml` exits 0
- `curl -sf http://100.64.0.1:3009/api/swagger >/dev/null`
- `docker ps --format '{{.Names}}'` on `docker-build` includes `lv3-gitea-runner`
- a smoke repository push creates a workflow run that completes successfully on the self-hosted runner
