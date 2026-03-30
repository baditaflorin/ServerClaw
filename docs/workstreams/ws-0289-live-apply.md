# Workstream ws-0289-live-apply: Live Apply ADR 0289 From Latest `origin/main`

- ADR: [ADR 0289](../adr/0289-directus-as-the-rest-graphql-data-api-layer-over-postgres.md)
- Title: Deploy Directus on `docker-runtime-lv3`, back it with managed Postgres, publish `data.lv3.org`, and verify REST and GraphQL access end to end
- Status: live_applied
- Branch: `codex/ws-0289-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0289-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secrets-injection`, `adr-0086-backup-and-recovery`, `adr-0191-immutable-guest-replacement`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0289-live-apply.md`, `docs/adr/0289-directus-as-the-rest-graphql-data-api-layer-over-postgres.md`, `docs/runbooks/configure-directus.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `roles/directus_postgres/`, `roles/directus_runtime/`, `roles/keycloak_runtime/`, `playbooks/directus.yml`, `playbooks/services/directus.yml`, `config/*catalog*.json`, `Makefile`, `tests/`, `receipts/image-scans/`, `receipts/live-applies/`

## Scope

- replace the placeholder Directus scaffold with a repo-managed Postgres, runtime, Keycloak, bootstrap, and verification implementation
- live apply the service from the latest `origin/main` baseline on the shared LV3 platform
- record enough branch-local evidence that a later merge or exact-main integration can proceed safely

## Non-Goals

- updating protected integration-only files before this branch is ready for the final `main` step
- treating Directus itself as the platform API gateway
- leaving GUI-only bootstrap steps undocumented or unautomated

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0289-live-apply.md`
- `docs/adr/0289-directus-as-the-rest-graphql-data-api-layer-over-postgres.md`
- `docs/runbooks/configure-directus.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `roles/directus_postgres/`
- `roles/directus_runtime/`
- `roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/directus_postgres/`
- `collections/ansible_collections/lv3/platform/roles/directus_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `playbooks/directus.yml`
- `playbooks/services/directus.yml`
- `scripts/directus_bootstrap.py`
- `config/api-gateway-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/secret-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/slo-catalog.json`
- `config/subdomain-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `Makefile`
- `tests/`
- `receipts/image-scans/`
- `receipts/live-applies/`

## Expected Live Surfaces

- a running Directus stack on `docker-runtime-lv3`
- a managed PostgreSQL database and role for Directus on `postgres-lv3`
- public publication at `https://data.lv3.org`
- public REST and GraphQL verification using repo-managed scoped credentials
- Keycloak-backed human sign-in for the Directus operator path

## Ownership Notes

- this workstream owns the Directus runtime, bootstrap automation, and branch-local live-apply evidence
- `docker-runtime-lv3`, `postgres-lv3`, and `nginx-lv3` are shared live surfaces, so replay must stay narrow and documented
- protected integration files remain deferred until the final merge-to-`main` step

## Verification

- `make converge-directus env=production` passed on 2026-03-30 with final recap
  `docker-runtime-lv3 : ok=274 changed=2 unreachable=0 failed=0 skipped=88`,
  `postgres-lv3 : ok=70 changed=4 unreachable=0 failed=0 skipped=23`,
  `nginx-lv3 : ok=40 changed=5 unreachable=0 failed=0 skipped=6`, and
  `localhost : ok=23 changed=0 unreachable=0 failed=0 skipped=7`.
- `python3 scripts/directus_bootstrap.py verify-public --base-url https://data.lv3.org ...`
  returned `{"status": "ok", "collection": "service_registry", "service_name": "directus", "rest_items": 1, "graphql_items": 1}` and wrote the fetched OpenAPI document to `receipts/live-applies/evidence/2026-03-30-adr-0289-directus-openapi.json`.
- Guest-local evidence confirms the runtime is up on `docker-runtime-lv3` with
  `directus` and `directus-openbao-agent` both healthy, `curl -fsS http://127.0.0.1:8055/server/health`
  returned `{"status":"ok"}`, and `curl -fsS http://127.0.0.1:8055/server/ping`
  returned `pong`.
- Public evidence confirms `data.lv3.org` resolves to `65.108.75.123` and
  `curl -fsS https://data.lv3.org/server/health` returned `{"status":"ok"}`.
- Branch-local automation and validation passed:
  `make syntax-check-directus`,
  `make preflight WORKFLOW=converge-directus`,
  `./scripts/validate_repo.sh agent-standards`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  `uv run --with pytest pytest -q tests/test_directus_playbook.py tests/test_directus_bootstrap.py tests/test_directus_runtime_role.py tests/test_directus_postgres_role.py tests/test_keycloak_runtime_role.py tests/test_compose_runtime_secret_injection.py tests/test_edge_publication_makefile.py tests/test_plausible_playbook.py`,
  and `make validate-generated-portals`.
- `make validate-generated-docs` is intentionally deferred to the exact-main
  integration step because it regenerates the protected top-level `README.md`
  status fragments that this workstream branch must not rewrite.

## Merge Criteria

- Directus is converged from committed automation and verified locally plus publicly
- ADR metadata, runbook notes, and workstream evidence explain the implementation variance from the original ADR text where needed
- repo generators, focused tests, and validation automation pass on the synchronized branch tree

## Remaining For Main Integration

- Refresh the protected top-level `README.md` generated status fragments and rerun
  `make validate-generated-docs`.
- Bump `VERSION`, update `changelog.md`, and update `versions/stack.yaml` only on
  the exact-`main` integration worktree after the final replay from `main`.
- Rerun the Directus live apply from exact `origin/main`, record the mainline
  receipt, and then finalize the ADR repo-version metadata.

## Live-Apply Notes

- A manual Hetzner DNS bridge was required during the brownout window for the
  legacy DNS write API. The temporary provider-side record was `data.lv3.org ->
  65.108.75.123` with record id `644d501af8a99d37d91f388ac4585349`; later
  governed replays observed the canonical state.

## Notes For The Next Assistant

- start from the latest `origin/main` before any final integration step
- do not reuse the placeholder `adr-0307-directus` artifacts; replace them with ADR 0289 truth
