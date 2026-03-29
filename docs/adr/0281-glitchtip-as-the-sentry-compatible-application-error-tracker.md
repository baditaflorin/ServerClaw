# ADR 0281: GlitchTip As The Sentry-Compatible Application Error Tracker

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform has strong infrastructure observability:

- **Grafana** dashboards over InfluxDB and Prometheus for host and service
  metrics
- **Loki** for log aggregation and log-based alerting
- **Tempo** for distributed traces
- **Langfuse** for LLM-specific trace evaluation and token accounting

None of these provide *application error tracking* in the sense of exception
aggregation, stack trace grouping, occurrence counting, and regression
detection across deployments:

- a Python exception in the mail-gateway service (ADR 0130) lands in Loki as
  a log line but is not grouped, deduplicated, or counted against a baseline
- a JavaScript runtime error in an Open WebUI session produces no structured
  error event
- when a service throws the same exception 200 times an hour, Loki captures
  all 200 lines but has no mechanism to say "this error is new since the last
  deploy and is occurring at a rising rate"

This gap means regressions are discovered late, often through user reports or
SLO breach alerts rather than through grouped error events correlated with the
deployment that introduced them.

GlitchTip is a CPU-only, open-source Sentry-compatible error tracker. It
accepts Sentry SDK events from any language, stores them in PostgreSQL,
groups them by fingerprint, and fires alerts when new issues appear or
existing issues regress.

## Decision

We will deploy **GlitchTip** as the platform's application error tracking
service.

### Deployment rules

- GlitchTip runs as a Docker Compose service on the docker-runtime VM using
  the existing PostgreSQL cluster as its backend database (ADR 0042)
- Authentication is delegated to Keycloak via OIDC (ADR 0063)
- The service is published under the platform subdomain model (ADR 0021) at
  `errors.<domain>`
- Email digest delivery uses the existing Stalwart mail platform (ADR 0130)
- Secrets (DSN keys, OIDC client credentials) are injected from OpenBao
  following ADR 0077

### SDK instrumentation rules

- all platform-owned Python services must initialise the Sentry SDK with the
  GlitchTip DSN at startup; this includes the mail-gateway, bootstrap scripts,
  and any Windmill Python workers where the Sentry SDK is supported
- JavaScript and TypeScript applications with a web front end must initialise
  the Sentry browser SDK
- DSN values are per-project and stored in OpenBao; they are never hardcoded
  in templates

### Alert routing

- new issue alerts route to the platform-ops Mattermost channel
- issues marked as regressions (re-opened after a resolved state) route to
  ntfy at high priority

## Consequences

**Positive**

- Application exceptions are grouped, counted, and correlated with deployments
  rather than being buried in log streams.
- Regression detection after a deploy surfaces within minutes instead of
  during the next user-reported incident.
- The Sentry-compatible SDK surface means instrumentation reuses an existing
  ecosystem of libraries across Python, JavaScript, and Go.
- GlitchTip stores all data in the existing PostgreSQL cluster, so there is no
  new database engine to operate.

**Negative / Trade-offs**

- Sentry SDK initialisation adds a small startup cost and an outbound network
  call from each instrumented service to GlitchTip.
- Services that use languages without a Sentry SDK (e.g. shell scripts) cannot
  report structured errors; those remain log-based.
- Error volumes from high-throughput services must be rate-limited at the SDK
  level to avoid filling the PostgreSQL errors tables.

## Boundaries

- GlitchTip tracks application-level errors and exceptions; it does not
  replace Loki for general log aggregation.
- GlitchTip does not replace Langfuse for LLM trace and evaluation tracking;
  they serve different diagnostic purposes.
- GlitchTip does not replace Grafana alerting for infrastructure metrics and
  SLO breach notifications.
- Performance monitoring (profiling, transaction traces) is not enabled at
  launch; Tempo covers distributed tracing for that purpose.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0130: Mail platform for transactional email
- ADR 0146: Langfuse for agent observability
- ADR 0197: Dify as the visual AI workflow canvas

## References

- <https://glitchtip.com/documentation>
