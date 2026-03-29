# ADR 0279: Grist As The No-Code Operational Spreadsheet Database

- Status: Accepted
- Implementation Status: Live applied on workstream branch
- Implemented In Repo Version: N/A
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
