# ADR 0283: Plausible Analytics As The Privacy-First Web Traffic Analytics Layer

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform monitors availability and performance of its public endpoints:

- **Uptime Kuma** tracks HTTP status and response time
- **Blackbox exporter** fires SLO alerts on probe failures
- **Grafana** dashboards display infrastructure metrics

None of these answer operator questions about *how* the public endpoints are
being used:

- which pages on Outline or the public edge are visited most frequently?
- which referral sources bring traffic to the platform's public services?
- does a newly published service endpoint receive any external traffic at all,
  or is it only used by internal operators?
- are there error pages or dead-end flows that users encounter before an
  SLO probe fires?

This visibility gap means capacity sizing, content prioritisation, and
user-facing changes are made without traffic evidence. The platform cannot
distinguish a service that is actively used by external parties from one that
has zero traffic.

Plausible Analytics is a CPU-only, open-source, cookie-free web analytics
service. It collects page view and referral data through a lightweight
JavaScript snippet, stores aggregated statistics in ClickHouse, and exposes
a dashboard without any personally identifiable information. It is
GDPR-compliant by design and does not require cookie consent banners.

## Decision

We will deploy **Plausible Analytics** as the privacy-first web traffic
analytics layer for public platform services.

### Deployment rules

- Plausible runs as a Docker Compose service on the docker-runtime VM; it
  ships with an embedded ClickHouse instance in the official compose bundle
- Authentication is delegated to Keycloak via OIDC (ADR 0063)
- The service is published under the platform subdomain model (ADR 0021) at
  `analytics.<domain>`
- ClickHouse data and Plausible PostgreSQL data are stored on named Docker
  volumes included in the backup scope (ADR 0086)
- Secrets (secret key base, OIDC client credentials, SMTP credentials) are
  injected from OpenBao following ADR 0077

### Site registration rules

- each public-facing subdomain that serves user-facing pages registers as a
  Plausible site; the registration is declared in the Ansible role's
  `defaults/main.yml` site list and applied idempotently
- internal-only services (monitoring, Gitea, Portainer) are registered as
  sites only if operators explicitly decide to track internal traffic
- the Plausible script snippet is added to the NGINX edge's standard include
  block so all served responses automatically include the tracker without
  per-service changes

### Data governance rules

- Plausible is configured to exclude bot traffic and known scraper user-agents
- IP addresses are never stored; Plausible's salted-hash approach is used as
  shipped
- data retention in ClickHouse follows the platform's standard analytics
  retention tier (12 months rolling)
- no Plausible event data is correlated with authenticated user identities;
  traffic analytics and identity management must remain scope-separated

## Consequences

**Positive**

- Operators gain real traffic evidence for capacity sizing, content decisions,
  and service promotion without compromising user privacy.
- Cookie-free collection means no consent banner changes are required for
  existing public services.
- Aggregated statistics are available in a dedicated UI and can be embedded
  as iframe panels in Grafana for operational dashboard inclusion.
- The JavaScript snippet delivered via the NGINX edge include block is a
  single change that instruments all current and future public services.

**Negative / Trade-offs**

- ClickHouse is a column-store database with a non-trivial memory footprint at
  startup (~200 MB baseline); the docker-runtime VM must have headroom for it.
- Plausible's aggregated model trades granularity for privacy; it cannot answer
  session-level or user-level questions by design, which is a feature but also
  a limitation for detailed funnel analysis.

## Boundaries

- Plausible tracks page views and referral sources for public web traffic; it
  does not replace Grafana for infrastructure metrics, Loki for application
  logs, or Langfuse for LLM interaction traces.
- Plausible does not track authenticated internal user activity or API traffic;
  those remain in the API gateway request log and Loki.
- Plausible event data is not correlated with Keycloak user sessions under
  any circumstance.
- A/B testing and conversion funnel features of Plausible are not in scope
  for the initial deployment.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0096: SLO probes and Blackbox exporter

## References

- <https://plausible.io/docs/self-hosting>
