# Workstream ws-0292-superset-live-apply: Live Apply ADR 0292 Superset From Latest `origin/main`

- ADR: [ADR 0292](../adr/0292-apache-superset-as-the-sql-first-business-intelligence-layer.md)
- Title: Deploy Apache Superset on `docker-runtime-lv3`, publish it at `bi.lv3.org`, register read-only SQL datasources, and verify the SQL-first BI surface end to end
- Status: in-progress
- Branch: `codex/ws-0292-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0292-live-apply`
- Owner: codex
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0042-postgresql-as-the-shared-relational-database`, `adr-0063-keycloak-sso-for-internal-services`, `adr-0077-compose-secret-injection-pattern`, `adr-0283-plausible-analytics-as-the-privacy-first-web-traffic-analytics-layer`
- Conflicts With: none

## Scope

- deploy Apache Superset on `docker-runtime-lv3` as a repo-managed Docker Compose service built from a pinned upstream base image
- store Superset metadata in PostgreSQL on `postgres-lv3` using a dedicated `superset` schema inside the shared `postgres` database
- delegate browser sign-in to Keycloak through a repo-managed OIDC client and publish the service at `bi.lv3.org`
- register read-only PostgreSQL datasources plus Plausible ClickHouse in the Superset metadata plane
- leave branch-local live-apply evidence, tests, and workstream state ready for the final exact-main replay and merge closeout

## Non-Goals

- replacing Grafana for operational alerting or replacing JupyterHub for notebook-driven analysis
- introducing a new time-series compatibility layer solely to translate InfluxDB 2 into a SQL datasource if upstream Superset support is absent
- modifying protected release truth until the final exact-main integration step

## Expected Repo Surfaces

- `docs/adr/0292-apache-superset-as-the-sql-first-business-intelligence-layer.md`
- `docs/runbooks/configure-superset.md`
- `docs/workstreams/ws-0292-superset-live-apply.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/superset.yml`
- `playbooks/services/superset.yml`
- `collections/ansible_collections/lv3/platform/roles/superset_postgres/`
- `collections/ansible_collections/lv3/platform/roles/superset_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `config/*catalog*.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `Makefile`
- `tests/`
- `receipts/live-applies/`
- `workstreams.yaml`

## Expected Live Surfaces

- the Superset runtime published privately on `docker-runtime-lv3`
- the public hostname `bi.lv3.org` on the shared NGINX edge
- a repo-managed Keycloak OIDC client for Superset
- a repo-managed metadata schema and read-only datasource role on the PostgreSQL primary
- committed evidence covering local health, public publication, datasource registration, and seeded dashboard verification

## Ownership Notes

- this workstream owns the Superset runtime, PostgreSQL bootstrap, Keycloak client, and live-apply receipts for ADR 0292 Superset
- `docker-runtime-lv3`, `postgres-lv3`, `nginx-lv3`, and the shared Keycloak runtime are shared live surfaces, so replay must stay within the governed playbook path and avoid unrelated mutations
- `ws-0292-live-apply` already exists on `origin/main` for the separately merged Lago ADR, so this Superset closeout uses the disambiguated workstream id `ws-0292-superset-live-apply` to preserve both histories safely
