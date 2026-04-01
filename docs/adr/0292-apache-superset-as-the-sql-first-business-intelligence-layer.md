# ADR 0292: Apache Superset As The SQL-First Business Intelligence Layer

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.129
- Implemented In Platform Version: 0.130.82
- Implemented On: 2026-04-01
- Date: 2026-03-29

## Context

The platform has two existing visualisation tools:

- **Grafana** (ADR monitoring stack) serves infrastructure and service metrics
  over time-series datasources (InfluxDB, Prometheus, Loki, Tempo). It is
  optimised for operational dashboards with time-range selectors and alert
  thresholds.
- **Plausible Analytics** (ADR 0283) serves web traffic analytics.

Neither tool is suited to ad-hoc SQL queries over relational operational data
in PostgreSQL. When operators need to answer questions like:

- how many annotation tasks per project were completed in Label Studio last week?
- what is the breakdown of LLM token usage by consumer in the last 30 days?
- which Windmill workflow executions failed most frequently by error class?
- what is the total storage consumed per MinIO bucket per service?

they currently resort to writing raw SQL in psql, constructing one-off scripts,
or querying through JupyterHub notebooks. There is no shared BI layer where
non-technical stakeholders can explore operational data through a
point-and-click interface.

Apache Superset is a CPU-only, open-source SQL-first BI and data exploration
platform. It connects to PostgreSQL, InfluxDB, ClickHouse (used by Plausible),
and dozens of other sources. It provides a no-code chart builder, a SQL Lab
for direct queries, and shareable dashboards.

## Decision

We will deploy **Apache Superset** as the shared SQL-first business intelligence
layer for operational data.

### Deployment rules

- Superset runs as a Docker Compose service on the docker-runtime VM
- it uses PostgreSQL as its own metadata database (ADR 0042) in a dedicated
  `superset` schema
- authentication is delegated to Keycloak via OIDC (ADR 0063)
- the service is published under the platform subdomain model (ADR 0021) at
  `bi.<domain>`
- secrets (database connection strings, OIDC credentials, secret key) are
  injected from OpenBao following ADR 0077

### Datasource registration rules

- each operational PostgreSQL database is registered as a datasource in the
  Ansible role; connection details come from OpenBao read-only credentials
- datasource connections use read-only PostgreSQL roles; Superset has no write
  access to any operational database
- the InfluxDB datasource is registered for time-series queries that benefit
  from chart-builder presentation rather than Grafana alerting presentation
- the Plausible ClickHouse database is registered as a datasource to allow
  custom traffic analytics dashboards beyond Plausible's built-in UI

### Dashboard governance

- platform-standard dashboards (LLM token usage, annotation throughput,
  workflow success rates) are defined as Superset export files in the Ansible
  role and imported idempotently on each converge
- operator-created ad-hoc dashboards are preserved across converges; they are
  not managed by Ansible and may be exported manually to version control

## Consequences

**Positive**

- Operational data in PostgreSQL becomes accessible to non-technical
  stakeholders without SQL knowledge or direct database access.
- Read-only datasource connections ensure Superset cannot modify production
  data regardless of user permissions.
- SQL Lab gives technical operators a browser-based SQL environment against
  operational databases without needing psql or JupyterHub for simple queries.
- Shared dashboards reduce the overhead of recurring operational reporting
  (weekly token usage, annotation queue health, cost allocation).

**Negative / Trade-offs**

- Superset adds another significant Python application with its own dependency
  tree and security surface; it must be kept patched.
- Superset's cache layer (Redis) adds a dependency if query caching is enabled;
  at launch caching is disabled to avoid introducing Redis as a new service.

## Boundaries

- Superset covers relational and analytical queries over operational data; it
  does not replace Grafana for infrastructure metrics, alerts, or SLO
  dashboards.
- Superset does not replace JupyterHub for code-based exploratory analysis or
  ML prototyping.
- Superset does not write to operational databases; it is a read-only BI
  layer.
- Superset is not used for real-time dashboards that require sub-second refresh;
  those remain in Grafana with its native streaming datasource support.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0283: Plausible Analytics as the privacy-first web traffic analytics layer
- ADR 0287: LiteLLM as the unified LLM API proxy and router
- ADR 0291: JupyterHub as the interactive notebook environment

## References

- <https://superset.apache.org/docs/installation/docker-compose>
