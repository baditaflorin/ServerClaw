# ADR 0289: Directus As The REST And GraphQL Data API Layer Over Postgres

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

Several operational data sets on the platform—equipment registers, service
catalogues, runbook metadata, on-call rotas, asset inventories—are currently
stored in PostgreSQL tables managed by ad-hoc Ansible tasks or hand-written
scripts. Accessing or updating these records requires either:

- a direct `psql` session (a GUI or shell step that bypasses access control)
- a bespoke FastAPI or Flask endpoint that must be written, deployed, and
  maintained per data set

Neither approach provides a consistent, authenticated, rate-limited HTTP
interface that Windmill workflows, n8n automations, and external operators
can call without knowing the underlying schema or SQL dialect.

Directus is a CPU-only, open-source data platform that introspects an
existing PostgreSQL schema and auto-generates a full REST API and a GraphQL
endpoint for every table and view. The REST API follows a predictable pattern
(`GET /items/{collection}`, `POST /items/{collection}`, etc.) and is
documented by an OpenAPI specification served at `/server/specs/oas`. Access
to each collection is governed by role-based permissions managed via the
Directus permissions API. There is no need to write application code to
expose a database table as an authenticated HTTP endpoint.

## Decision

We will deploy **Directus** as the REST and GraphQL data API layer for
operational data sets stored in PostgreSQL that do not belong to a
service-specific application.

### Deployment rules

- Directus runs as a Docker Compose service on the docker-runtime VM using
  the official `directus/directus` image
- Authentication is delegated to Keycloak via OIDC (ADR 0063); local
  Directus accounts are disabled except for the break-glass admin account
  whose password is stored in OpenBao (ADR 0077)
- The service is published under the platform subdomain model (ADR 0021) at
  `data.<domain>`; the REST API is at `data.<domain>/items/` and the GraphQL
  endpoint at `data.<domain>/graphql`
- Directus connects to the shared PostgreSQL cluster (ADR 0042) using a
  dedicated read-write role scoped to the `directus` schema; it does not
  have DDL permissions outside that schema
- All Directus configuration (roles, permissions, webhooks, flows) is
  exported to a JSON snapshot via the Schema/Snapshot API and committed to
  the Ansible role; the snapshot is applied idempotently on converge
- Secrets (database credentials, OIDC client credentials, secret key) are
  injected from OpenBao following ADR 0077

### API-first operation rules

- New operational data sets are added by creating a PostgreSQL table in the
  `directus` schema and running a Directus schema sync; Directus
  auto-generates the REST and GraphQL endpoints without additional code
- Collection permissions (who can read, create, update, delete which fields)
  are managed via the Directus permissions REST API
  (`PATCH /permissions/{id}`); permissions are declared in the Ansible role
  defaults and applied by the seed task
- Windmill and n8n workflows interact with operational data exclusively
  through the Directus REST or GraphQL API using scoped API tokens stored
  in OpenBao; direct PostgreSQL connections from automation scripts are
  prohibited for Directus-managed collections
- The Directus Flows feature (built-in automation) is disabled; automation
  logic lives in Windmill and n8n, which call Directus as a data API
- Webhooks may be configured to push item creation/update events to NATS
  JetStream (ADR 0276) for downstream automation triggers

### Data governance rules

- the `directus` PostgreSQL schema is the exclusive home of operational
  data sets managed by Directus; application-specific tables live in their
  service's own schema
- all Directus-managed tables include `created_at`, `updated_at`, and
  `created_by` audit columns managed by Directus automatically
- the OpenAPI specification at `/server/specs/oas` is fetched during CI and
  committed as a versioned artefact; consumers pin to a spec version and
  are alerted on breaking changes

## Consequences

**Positive**

- Any PostgreSQL table in the `directus` schema becomes an authenticated,
  rate-limited HTTP endpoint in minutes with no application code written.
- Windmill and n8n workflows have a consistent, predictable REST API for
  operational data regardless of which table they query.
- The schema snapshot in the Ansible role means Directus configuration is
  fully reproducible after a fresh deploy; no manual GUI steps are required.
- Directus field-level permissions allow read-only API tokens to be issued
  for specific collections without exposing unrelated data sets.

**Negative / Trade-offs**

- Directus adds a layer of indirection over PostgreSQL; complex joins and
  aggregations that are natural in SQL require either a PostgreSQL view or
  a GraphQL query with nested relations, which may be less intuitive.
- The auto-generated OpenAPI spec is verbose; consumers should import it
  into a client generator rather than reading it manually.

## Boundaries

- Directus manages operational data sets without service owners; it is not
  a replacement for application-specific APIs written by service teams.
- Directus does not manage secrets or authentication tokens; those remain
  in OpenBao.
- The Directus admin panel is available for visual schema inspection and
  manual data corrections; it is not the primary interface for routine
  operations, which are performed via API.
- Directus is not used as a CMS for public-facing content; content
  management for public pages is out of scope.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://docs.directus.io/reference/introduction.html>
- <https://docs.directus.io/reference/graphql.html>
