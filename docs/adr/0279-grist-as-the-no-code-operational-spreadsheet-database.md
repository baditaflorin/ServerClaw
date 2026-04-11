# ADR 0279: Grist As The No-Code Operational Spreadsheet Database

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.105
- Implemented In Platform Version: 0.130.60
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

Operations teams managing the platform encounter a class of structured data
that does not fit well into the tools already deployed:

- **Outline** (ADR 0199) is a narrative wiki; it is not suited to structured
  tables that require filtering, formula columns, or row-level updates
- **Plane** (ADR 0193) manages project tasks and milestones, not arbitrary
  relational tables
- **NetBox** (ADR 0046) models network topology objects with a fixed schema;
  custom operational tables (e.g. vendor contacts, capacity allocation
  trackers, approval registers) require NetBox customisation fields that
  quickly become unmaintainable
- **PostgreSQL** is authoritative for service data but requires SQL knowledge
  and has no built-in UI for operator-managed tables

Examples of structured operational data that currently has no home:

- hardware maintenance schedules and asset lifecycles
- cost and capacity allocation tables reviewed in monthly operations reviews
- incident post-mortem action trackers that need a spreadsheet-like view
- procurement and approval registers cross-referenced with NetBox

Grist is a CPU-only, open-source spreadsheet-database hybrid. It stores
documents as SQLite files, supports Python formula columns, and exposes a
REST API. It is designed exactly for operations teams who need spreadsheet
ergonomics over relational data without writing SQL.

## Decision

We will deploy **Grist** as the shared no-code operational spreadsheet
database.

### Deployment rules

- Grist runs as a Docker Compose service on the docker-runtime VM
- Authentication is delegated to Keycloak via OIDC following the standard
  SSO pattern (ADR 0063)
- Document files are stored on a named Docker volume and are included in the
  backup scope (ADR 0086)
- The service is published under the platform subdomain model (ADR 0021) at
  `grist.<domain>`

### Data ownership rules

- Grist documents are owned by the team or individual who creates them; there
  is no single global schema
- Grist is the authoritative source for operational data that lives entirely
  within its documents; it is not a shadow copy of PostgreSQL data
- Where a Grist document references platform objects (hosts, services, IPs),
  those references are advisory; the authoritative record remains in NetBox or
  PostgreSQL

### Integration conventions

- Windmill and n8n may call the Grist REST API to read or write rows as part
  of automation flows
- Grist documents may embed charts and calculated columns using Python
  formulas; those computations run inside the Grist container, CPU-only
- Gotenberg (ADR 0278) may be used to render a Grist-exported HTML report
  as a PDF for distribution

## Consequences

**Positive**

- Operations teams gain a structured, shareable data layer without needing to
  write SQL or maintain a bespoke database schema.
- Grist's formula engine runs inside the container with no GPU requirement and
  negligible CPU overhead at operational data scales.
- The REST API makes Grist documents addressable from Windmill and n8n without
  a custom integration layer.
- Keeping operational tables in Grist prevents schema drift inside PostgreSQL
  where mixed operational and application data increases maintenance burden.

**Negative / Trade-offs**

- Grist documents are SQLite files, not PostgreSQL; backup and integrity
  tooling differs from the primary database cluster.
- Grist does not enforce referential integrity across documents or against
  external systems; cross-document consistency is operator responsibility.

## Boundaries

- Grist is not used for application runtime data; services store their
  operational state in PostgreSQL.
- Grist is not a replacement for NetBox; network topology and IP management
  remain in NetBox.
- Grist is not used for long-term metric or log data; those stay in InfluxDB
  and Loki.

## Operational Lessons (2026-04-05)

An incident on 2026-04-05 exposed several non-obvious runtime requirements
that are now encoded in the role defaults and nginx_edge_publication CSP
overrides. See `docs/runbooks/configure-grist.md` for the full postmortem.

**NGINX CSP must allow `'unsafe-inline'` for `script-src`.**
Grist injects a `<script>window.gristConfig = {...}</script>` inline bootstrap
block on every page. Without `'unsafe-inline'` in `script-src`, the client
cannot determine the organisation from the URL and throws
`Cannot figure out what organization the URL is for` before any login flow
begins. The `nginx_edge_publication` role now carries a `grist.example.com`
override in `public_edge_security_headers_overrides`.

**`GRIST_SERVE_SAME_ORIGIN=true` is required for single-org mode.**
Without it, Grist cannot resolve the organisation from the same-origin URL
pattern in single-org deployments. This variable must be set alongside
`GRIST_SINGLE_ORG`.

**`GRIST_FORCE_LOGIN=false` with `GRIST_ANONYMOUS_PLAYGROUND=false` is the
correct public-sharing posture.**
Setting `GRIST_FORCE_LOGIN=true` blocks unauthenticated access to documents
that have been explicitly marked public by their owner. The correct combination
is `GRIST_FORCE_LOGIN=false` (allows public document links to work) plus
`GRIST_ANONYMOUS_PLAYGROUND=false` (prevents anonymous users from creating
new documents or accessing the org workspace without authentication).

**Container restarts pick up env file changes only with `--force-recreate`.**
`docker compose restart` reuses the cached container environment. Changed
`env_file` values are only picked up via `docker compose up -d --force-recreate`.

**The `nginx_edge_publication` preliminary render required a missing default.**
The `public_edge_site_tls_materials` variable lacked a default value, causing
the preliminary NGINX config render to fail with an `UndefinedError` before
the final TLS-aware render ran. The variable is now defaulted to `{}` in
`nginx_edge_publication/defaults/main.yml`.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0046: NetBox for network documentation
- ADR 0063: Keycloak SSO for internal services
- ADR 0086: Backup and recovery for stateful services
- ADR 0193: Plane as the task board
- ADR 0199: Outline as the living knowledge wiki
- ADR 0278: Gotenberg as the document-to-PDF rendering service

## References

- <https://support.getgrist.com/self-managed/>
