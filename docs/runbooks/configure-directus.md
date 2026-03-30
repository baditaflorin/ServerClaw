# Configure Directus

Directus is the repo-managed REST and GraphQL operational data API published at
`https://data.lv3.org`. The runtime lives on `docker-runtime-lv3`, stores its
state in the dedicated PostgreSQL database `directus` on `postgres-lv3`, and
delegates routine browser sign-in to Keycloak.

## Repo Surfaces

- Root playbook: `playbooks/directus.yml`
- Service wrapper: `playbooks/services/directus.yml`
- Runtime role: `roles/directus_runtime/`
- PostgreSQL role: `roles/directus_postgres/`
- Bootstrap helper: `scripts/directus_bootstrap.py`

## Implementation Variance From ADR 0289

- Directus 11.17.0 stores both system tables and governed collections in the
  `public` schema of the dedicated `directus` database. The repo therefore
  enforces isolation at the database boundary, not by a separate PostgreSQL
  schema.
- The Directus Schema/Snapshot API covers the data model but not the complete
  access model. Converge therefore uses the Directus REST API to bootstrap the
  governed collection schema and a deterministic SQL seed to manage roles,
  policies, permissions, and the durable service token.
- Local Directus auth remains available for the break-glass admin account.
  Routine browser access is expected to use the Keycloak OIDC path.

## Controller-Local Artifacts

The converge path creates and reuses these controller-local files:

- `.local/directus/database-password.txt`
- `.local/directus/key.txt`
- `.local/directus/secret.txt`
- `.local/directus/admin-password.txt`
- `.local/directus/service-registry-token.txt`
- `.local/keycloak/directus-client-secret.txt`

## Converge

Run the syntax check first:

```bash
make syntax-check-directus
```

Run the Directus preflight so the shared edge publication bootstrap artifacts and
required controller-local secrets are present before the live converge:

```bash
make preflight WORKFLOW=converge-directus
```

Run the live converge from the repo root:

```bash
make converge-directus env=production
```

`converge-directus` requires:

- `BOOTSTRAP_KEY` or the default controller SSH key path
- `HETZNER_DNS_API_TOKEN` in the environment so the playbook can publish
  `data.lv3.org`
- The Hetzner legacy `dns.hetzner.com` write API to be outside its scheduled
  brownout window during the DNS migration period, or the zone already migrated
  and managed through the newer Hetzner Console workflow

The playbook performs these steps:

1. Ensures the `data.lv3.org` Hetzner DNS record exists.
2. Creates or reconciles the PostgreSQL role and dedicated `directus`
   database on `postgres-lv3`.
3. Creates the Directus runtime secrets, Keycloak client secret mirror,
   compose env, and runtime on `docker-runtime-lv3`.
4. Bootstraps the governed `service_registry` collection and restarts
   Directus once if schema changes were applied.
5. Seeds the Directus access model in PostgreSQL.
6. Publishes Directus through the shared NGINX edge and verifies the public
   health, OIDC redirect, REST token flow, and GraphQL token flow.

## Verification

Local runtime verification:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'docker compose --file /opt/directus/docker-compose.yml ps && curl -fsS http://127.0.0.1:8055/server/health'
```

Public health verification:

```bash
curl -fsS https://data.lv3.org/server/health
```

Public end-to-end API and OIDC verification:

```bash
python3 scripts/directus_bootstrap.py verify-public \
  --base-url https://data.lv3.org \
  --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/directus/service-registry-token.txt \
  --collection service_registry \
  --expected-service-name directus \
  --expected-sso-host sso.lv3.org
```

The verification helper checks:

- `GET /server/health`
- `GET /server/ping`
- `GET /server/specs/oas`
- `GET /auth/login/keycloak` redirects to `sso.lv3.org`
- token-authenticated `GET /items/service_registry`
- token-authenticated GraphQL query on `/graphql`

## Recovery Notes

- Re-run `make converge-directus` for drift correction or after rebuilding
  `docker-runtime-lv3`, `postgres-lv3`, or the shared edge configuration.
- If the converge fails on the localhost DNS task with a provider error that
  mentions the DNS Console brownout, wait for the current brownout window to
  end and rerun `make converge-directus env=production`. The role now reports
  the provider message directly so the brownout is distinguishable from a repo
  bug or a credential failure.
- If a brownout blocks publication and the live change cannot wait, create the
  exact missing `data.lv3.org` A record manually in Hetzner, record the
  provider-side record id in the live-apply receipt, and rerun
  `make converge-directus env=production` so the repo-managed converge observes
  the canonical state again.
- If a new collection or field exists in Directus metadata but not GraphQL,
  restart Directus once and rerun the public verification. The role already
  performs this restart automatically when schema bootstrap changes occur.
- If OIDC login breaks, reconverge `playbooks/keycloak.yml` and then rerun
  `make converge-directus` so the runtime picks up the latest mirrored client
  secret.
- If PostgreSQL inspection is needed during recovery, remember that Directus
  system tables and repo-managed collections both live in the `public` schema
  of the dedicated `directus` database.
