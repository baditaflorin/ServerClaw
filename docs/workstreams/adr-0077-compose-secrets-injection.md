# Workstream ADR 0077: Compose Runtime Secrets Injection Via OpenBao Agent

- ADR: [ADR 0077](../adr/0077-compose-runtime-secrets-injection.md)
- Title: Replace .env file secrets in Docker Compose stacks with OpenBao Agent sidecar injection via tmpfs
- Status: ready
- Branch: `codex/adr-0077-compose-secrets-injection`
- Worktree: `../proxmox_florin_server-compose-secrets-injection`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0025-docker-compose-stacks`, `adr-0047-short-lived-creds`, `adr-0065-secret-rotation-automation`
- Conflicts With: any workstream that writes new `.env` files to compose directories
- Shared Surfaces: `roles/docker_compose_stack`, all Compose stack templates on `docker-runtime-lv3`, `config/image-catalog.json`

## Scope

- add `openbao-agent` sidecar service to the `roles/docker_compose_stack` role template
- template `openbao-agent.hcl.j2` for configurable secret paths and env file output
- update `roles/docker_compose_stack` to: provision AppRole credentials in OpenBao, write `role_id` and `secret_id` to restricted paths, remove existing `.env` files
- migrate the following Compose stacks to sidecar injection (priority order): grafana, windmill, mattermost, keycloak, open-webui
- add `make validate` check that no `*.env` files exist in the compose directory on the controller
- add `config/image-catalog.json` entry for `openbao/openbao-agent`
- document the migration guide in `docs/runbooks/compose-secrets-injection.md`

## Non-Goals

- migrating non-Compose services (systemd-managed services continue to use Ansible lookup plugin)
- dynamic secret generation (dynamic DB credentials from OpenBao are a follow-on task)

## Expected Repo Surfaces

- `roles/docker_compose_stack/templates/openbao-agent.hcl.j2`
- updated `roles/docker_compose_stack/tasks/main.yml`
- updated Compose templates for grafana, windmill, mattermost, keycloak, open-webui
- updated `config/image-catalog.json` (openbao-agent image)
- `docs/runbooks/compose-secrets-injection.md`
- `docs/adr/0077-compose-runtime-secrets-injection.md`
- `docs/workstreams/adr-0077-compose-secrets-injection.md`
- `workstreams.yaml`

## Expected Live Surfaces

- grafana, windmill, mattermost, keycloak, and open-webui Compose stacks running with OpenBao Agent sidecar
- no `.env` files in `/opt/<stack>/` directories on `docker-runtime-lv3`
- AppRole credentials at `/opt/<stack>/openbao/` (mode 0600, root only)
- secrets visible via `vault kv get secret/prod/<stack>/` after rotation

## Verification

- `ls /opt/grafana/*.env` returns no files on `docker-runtime-lv3`
- `docker logs grafana-openbao-agent-1` shows successful secret fetch and render
- rotate `secret/prod/grafana/admin_password` in OpenBao; within 5 minutes, Grafana container reflects the new password without restart
- `make validate` fails if a `.env` file is committed to the repo

## Merge Criteria

- all five priority stacks are migrated and healthy on staging before production migration
- secret rotation test passes for at least one migrated stack
- the `.env` validation gate is integrated into `make validate`
- migration runbook is complete and reviewed

## Notes For The Next Assistant

- migrate grafana first — it is the least security-critical and easiest to verify (admin password change is immediately visible)
- the AppRole provisioning in OpenBao must use per-stack policies; do not share a single AppRole across all stacks
- test the tmpfs volume behaviour on container restart: verify secrets are re-fetched by the agent, not cached in a dead tmpfs
