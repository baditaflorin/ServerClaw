# Workstream ADR 0077: Compose Runtime Secrets Injection Via OpenBao Agent

- ADR: [ADR 0077](../adr/0077-compose-runtime-secrets-injection.md)
- Title: Replace compose-directory .env secrets with OpenBao Agent sidecar injection backed by host tmpfs
- Status: live_applied
- Branch: `codex/adr-0077-compose-secrets-injection`
- Worktree: `.worktrees/adr-0077`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0025-docker-compose-stacks`, `adr-0047-short-lived-creds`, `adr-0065-secret-rotation-automation`
- Conflicts With: any workstream that writes new `.env` files to compose directories
- Shared Surfaces: `roles/common/tasks/openbao_compose_env.yml`, Compose stack templates on `docker-runtime-lv3`, `config/image-catalog.json`, `scripts/validate_repo.sh`

## Scope

- add a shared OpenBao Agent helper under `roles/common/`
- template `openbao-agent.hcl.j2` for configurable AppRole auth and runtime env output under `/run/lv3-secrets/<service>/runtime.env`
- provision per-service AppRole credentials, write `role_id` and `secret_id` to `/opt/<service>/openbao/`, and remove legacy compose-directory `.env` files
- migrate the current Compose-managed secret consumers on `docker-runtime-lv3`: windmill, mattermost, keycloak, open-webui, netbox, platform-context, and the mail-platform gateway
- add a `make validate` guard that fails when any `*.env` file is present in the repository checkout
- reuse the pinned `openbao_runtime` image contract for the OpenBao Agent sidecars
- document the migration guide in `docs/runbooks/compose-secrets-injection.md`

## Non-Goals

- migrating non-Compose services (systemd-managed services continue to use Ansible lookup plugin)
- dynamic secret generation (dynamic DB credentials from OpenBao are a follow-on task)

## Expected Repo Surfaces

- `roles/common/templates/openbao-agent.hcl.j2`
- `roles/common/tasks/openbao_compose_env.yml`
- updated Compose templates and runtime roles for windmill, mattermost, keycloak, open-webui, netbox, platform-context, and mail-platform
- updated `config/image-catalog.json` usage for the shared OpenBao server/agent image contract
- `docs/runbooks/compose-secrets-injection.md`
- `docs/adr/0077-compose-runtime-secrets-injection.md`
- `docs/workstreams/adr-0077-compose-secrets-injection.md`
- `workstreams.yaml`

## Expected Live Surfaces

- windmill, mattermost, keycloak, open-webui, netbox, platform-context, and the mail-platform gateway running with OpenBao Agent sidecars once applied
- no legacy `.env` files in `/opt/<service>/` compose directories on `docker-runtime-lv3`
- AppRole credentials at `/opt/<stack>/openbao/` (mode 0600, root only)
- runtime env files present only under `/run/lv3-secrets/<service>/runtime.env`

## Verification

- `make validate`
- `make syntax-check-windmill`
- `make syntax-check-keycloak`
- `make syntax-check-mattermost`
- `make syntax-check-open-webui`
- `make syntax-check-netbox`
- `make syntax-check-rag-context`
- `make syntax-check-mail-platform`
- `make validate` fails if a `.env` file is committed to the repo

## Merge Criteria

- all current Compose-managed secret consumers on `docker-runtime-lv3` are migrated in repository automation
- secret rotation test passes for at least one migrated stack
- the `.env` validation gate is integrated into `make validate`
- migration runbook is complete and reviewed

## Live Apply Outcome

- Applied from `main` on 2026-03-23 with repo version `0.86.0` and platform version `0.39.0`
- All migrated services on `docker-runtime-lv3` now render runtime secrets under `/run/lv3-secrets/<service>/runtime.env` via healthy OpenBao Agent sidecars

## Notes For The Next Assistant

- Grafana is intentionally not part of the final implementation because the current mainline still runs it as a package-managed service on `monitoring-lv3`
- each service now has a dedicated AppRole and a dedicated `kv/data/services/<service>/runtime-env` payload
- the implementation uses host `/run` rather than a Docker named volume because Compose resolves `env_file` on the host filesystem
