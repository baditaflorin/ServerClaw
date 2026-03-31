# ADR 0303: pgaudit For PostgreSQL Query And Privilege Change Audit Logging

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

PostgreSQL on `postgres-lv3` (ADR 0026) is the platform's shared relational
database. It stores application data for Keycloak, Gitea, Langfuse, Plane,
Outline, n8n, NetBox, Windmill, One-API, Superset, and several other services.
All of those services share the same PostgreSQL instance with per-service
databases and roles.

The current observability for PostgreSQL covers:

- query performance via Prometheus `postgres_exporter` metrics in Grafana
- replication lag via streaming replica monitoring on `postgres-replica-lv3`
- backup state via PBS and Restic (ADR 0302)

What is not covered is a structured record of **who ran which query or DDL
statement and when**. Without this:

- a privilege escalation inside a compromised service container is undetectable
  until the attacker reads or modifies data
- a misconfigured Windmill script that accidentally runs a `DROP TABLE` or
  `TRUNCATE` against the wrong database produces no audit trail for
  post-incident forensics
- compliance verification that only authorised roles accessed production data is
  not possible without a query log

pgaudit (`pgaudit/pgaudit`) is the de facto PostgreSQL audit extension. It is
maintained by the PostgreSQL Audit Extension maintainers and emits structured
audit log lines through PostgreSQL's existing logging path. Those log lines are
machine-parseable and ship directly to Loki via the existing Alloy agent on
`postgres-lv3`.

## Decision

We will enable **pgaudit** on the production PostgreSQL instance and configure it
to emit structured session and object audit logs routed to Loki.

### Deployment rules

- pgaudit is enabled by adding `shared_preload_libraries = 'pgaudit'` to
  `postgresql.conf` managed by the Ansible role for `postgres-lv3`
- the pgaudit package version follows the extension build compatible with the
  deployed PostgreSQL major version
- enabling pgaudit requires a PostgreSQL restart; this is coordinated as a
  maintenance-window operation (ADR 0080) with a pre-restart health probe
  verification

### Audit scope configuration

pgaudit is configured at two levels:

**Global session audit** (`pgaudit.log` in `postgresql.conf`):
- `DDL`: all CREATE, ALTER, DROP, TRUNCATE statements
- `ROLE`: all GRANT, REVOKE, CREATE ROLE, ALTER ROLE, DROP ROLE statements

**Connection visibility** (standard PostgreSQL logging):
- `log_connections = on`: every successful connection is logged with user and database
- `log_disconnections = on`: every disconnection is logged with session duration
- connection events are not a separate `pgaudit.log` class; they are captured
  by PostgreSQL's native connection logging and parsed alongside pgaudit lines

**Per-object audit** (via `pgaudit.role` plus object grants):
- a dedicated no-login audit role is configured in `pgaudit.role`
- the `windmill` and `n8n` sensitive tables listed in
  `config/pgaudit/sensitive-tables.yaml` grant object-audit privileges to that
  role; this enables fine-grained tracing of automation-initiated access
  without logging every query for every service

### Log format and routing

- pgaudit log lines follow the format:
  `AUDIT: SESSION,<count>,<count>,<class>,<command>,<object_type>,<object>,<statement>,<param>`
- the Alloy agent on `postgres-lv3` is configured with a pipeline stage that
  parses pgaudit-tagged lines into structured Loki labels:
  `{job="postgres-audit", db="<db>", db_role="<role>", command_class="<class>"}`
- the same pipeline parses `connection authorized:` lines from PostgreSQL's
  standard connection logging and turns them into Prometheus counters labeled
  by database and role
- the structured labels enable Loki queries such as "all DDL statements in the
  last 24 hours by the `keycloak` role" without a full-text scan
- the Prometheus scrape of Alloy on `postgres-lv3` exposes:
  - `postgres_audit_events_total`
  - `postgres_connection_authorized_total`
  - `postgres_unknown_connection_events_total`

### Alert rules

- a Prometheus rule alerts if more than 10 ROLE-class events (privilege changes)
  occur within 5 minutes from a single role; this is a signal of either a
  runaway automation loop or a privilege escalation attempt
- any successful connection event from a database role that is not in the
  `config/pgaudit/approved-roles.yaml` list triggers:
  - the `PostgresUnknownRoleConnection` alert
  - an ntfy critical notification (ADR 0299)
  - a NATS `platform.security.pgaudit_unknown_role` event published by a local
    Alertmanager relay on `monitoring-lv3`

## Consequences

**Positive**

- every DDL statement and privilege change in production PostgreSQL is logged with
  session identity and statement text; post-incident forensics becomes feasible
- the Loki structured labels enable fast targeted queries without exporting logs to
  an external system
- the operational overhead remains bounded because only `DDL`, `ROLE`, and the
  explicitly granted sensitive objects are audited
- per-object audit for high-risk automation roles (Windmill, n8n) provides
  fine-grained traceability without logging every service's routine SELECT

**Negative / Trade-offs**

- DDL audit logging adds write volume to the PostgreSQL log file and to Loki; the
  Loki retention policy and disk budget for `monitoring-lv3` must account for the
  additional log stream
- per-parameter logging (`pgaudit.log_parameter = on`) is not enabled by default
  because it logs query parameters in plaintext, which could expose sensitive
  values if a developer accidentally passes credentials as query parameters; it
  can be enabled per-session for debugging but must not be left on permanently
- the PostgreSQL restart required at first enablement is a brief unavailability
  window for all services sharing the instance

## Boundaries

- pgaudit covers PostgreSQL query and privilege audit; it does not cover
  application-layer access control decisions; those remain the responsibility of
  Keycloak (ADR 0056) and service-level RBAC
- pgaudit does not monitor queries to the PostgreSQL replica; the replica is
  read-only and its query log is less critical, but a future ADR may extend audit
  coverage to the replica
- pgaudit log retention in Loki follows the standard Loki retention policy; long-
  term compliance evidence archival is out of scope for this ADR

## Related ADRs

- ADR 0026: Dedicated PostgreSQL VM baseline
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0066: Structured mutation audit log
- ADR 0080: Maintenance window and change suppression protocol
- ADR 0097: Alerting routing and oncall runbook model
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0299: Ntfy as the push notification channel
- ADR 0300: Falco for container runtime security monitoring

## References

- <https://github.com/pgaudit/pgaudit>
