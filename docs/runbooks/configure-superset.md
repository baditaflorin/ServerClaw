# Configure Superset

Superset is the repo-managed SQL-first business intelligence surface published
at `https://bi.example.com`. The runtime lives on `docker-runtime`, stores its
metadata in the `superset` schema of the shared `postgres` database on
`postgres`, and delegates routine browser sign-in to Keycloak.

## Repo Surfaces

- Root playbook: `playbooks/superset.yml`
- Service wrapper: `playbooks/services/superset.yml`
- PostgreSQL role: `roles/superset_postgres/`
- Runtime role: `roles/superset_runtime/`
- Bootstrap helper: `scripts/superset_bootstrap.py`

## Implementation Variance From ADR 0292

- The current live contract registers read-only PostgreSQL datasources and the
  Plausible ClickHouse datasource, but it does not register InfluxDB. Superset
  remains the SQL-first BI layer without introducing an extra translation layer
  solely to expose InfluxDB 2 through a governed SQL contract.
- Managed datasources and the landing dashboard are reconciled through the
  repo-managed `scripts/superset_bootstrap.py` helper instead of importing a
  native Superset export bundle. The helper is deterministic and idempotently
  re-applies only the managed datasource, dataset, chart, and dashboard
  objects.
- Local Superset database auth remains available for the repo-managed
  break-glass admin account so public API verification can prove the seeded
  datasource inventory and dashboard contract after deploy. Routine browser
  access is expected to use the Keycloak OIDC path.

## Controller-Local Artifacts

The converge path creates and reuses these controller-local files:

- `.local/superset/database-password.txt`
- `.local/superset/reader-password.txt`
- `.local/superset/secret-key.txt`
- `.local/superset/admin-password.txt`
- `.local/superset/postgres-databases.json`
- `.local/superset/verify-public-report.json`
- `.local/keycloak/superset-client-secret.txt`

## Converge

Run the syntax check first:

```bash
make syntax-check-superset
```

Run the Superset preflight so the shared edge publication bootstrap artifacts
and required controller-local secrets are present before the live converge:

```bash
make preflight WORKFLOW=converge-superset
```

Run the live converge from the repo root:

```bash
make converge-superset env=production
```

`converge-superset` requires:

- `BOOTSTRAP_KEY` or the default controller SSH key path
- `HETZNER_DNS_API_TOKEN` in the environment so the playbook can publish
  `bi.example.com`
- functional reachability from `docker-runtime` to `postgres` and the
  shared Keycloak realm

The playbook performs these steps:

1. Ensures the `bi.example.com` Hetzner DNS record exists.
2. Creates or reconciles the `superset` metadata schema, the `superset`
   metadata role, and the `superset_reader` datasource role on `postgres`.
3. Mirrors the generated database credentials and datasource catalog to the
   controller, then creates the Superset runtime secrets and Keycloak client
   secret mirror on `docker-runtime`.
4. Builds the pinned Superset image, starts the runtime with OpenBao-injected
   env, runs the Superset metadata migrations, and reconciles the repo-managed
   admin user.
5. Registers the managed PostgreSQL datasources plus the optional Plausible
   ClickHouse datasource and seeds the landing dashboard.
6. Publishes Superset through the shared NGINX edge and verifies the public
   health, Keycloak redirect, datasource inventory, and landing dashboard
   contract.

## Verification

Local runtime verification:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'docker compose --file /opt/superset/docker-compose.yml ps && curl -fsS http://127.0.0.1:8105/health'
```

Public health verification:

```bash
curl -fsS https://bi.example.com/health
```

Public end-to-end API and OIDC verification:

```bash
python3 scripts/superset_bootstrap.py verify-public \
  --base-url https://bi.example.com \
  --expected-postgres-databases-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/superset/postgres-databases.json \
  --database-prefix PostgreSQL \
  --expected-dashboard "LV3 Platform Database Inventory" \
  --expected-chart "PostgreSQL Databases" \
  --expected-sso-host sso.example.com \
  --admin-username admin \
  --admin-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/superset/admin-password.txt \
  --expected-extra-database "Plausible ClickHouse" \
  --report-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/superset/verify-public-report.json
```

The verification helper checks:

- `GET /health`
- `GET /login/keycloak` redirects to `sso.example.com`
- database-authenticated `POST /api/v1/security/login`
- `GET /api/v1/database`
- `GET /api/v1/chart`
- `GET /api/v1/dashboard`

## Recovery Notes

- Re-run `make converge-superset` for drift correction or after rebuilding
  `docker-runtime`, `postgres`, or the shared edge configuration.
- If public verification fails after a successful local converge, rerun
  `playbooks/keycloak.yml` and then `make converge-superset` so the runtime
  picks up the latest mirrored client secret.
- If the runtime fails to publish after a Docker bridge-chain loss on
  `docker-runtime`, rerun `make converge-superset`. The role includes the
  Docker nat-chain recovery path before the published ports are recreated.
- If the managed datasource inventory drifts from the current PostgreSQL
  database list, rerun the full converge so the datasource catalog is refreshed
  from `postgres` before the managed Superset metadata objects are
  reconciled.
