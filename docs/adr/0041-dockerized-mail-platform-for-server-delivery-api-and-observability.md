# ADR 0041: Dockerized Mail Platform For Server Delivery, API Automation, And Grafana Observability

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.43.0
- Implemented In Platform Version: 0.21.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform already has:

- a dedicated Docker runtime VM for containerized application workloads under ADR 0023
- a dedicated monitoring VM with Grafana and InfluxDB under ADR 0011
- a host and guest access model centered on named non-root identities
- notification plumbing that currently depends on an external sendmail endpoint

It does not yet have a first-class, self-hosted mail platform that is:

1. reachable from the platform when the Proxmox host, guests, and future applications need to send mail
2. rich enough to support both outbound delivery and future inbound mailbox handling
3. observable in Grafana with message counts, queue state, rejection rates, delivery failures, and other operational details
4. programmable through a durable CRUD-capable API that can be used safely by the server itself and by other LLM agents
5. resilient enough to keep accepting locally generated mail even when the primary mail path is unhealthy

Because this repository already established the Docker runtime VM as the home for long-running containerized services, the mail platform should follow that boundary instead of introducing a one-off container workload directly on the Proxmox host.

The decision also has to respect operational reality:

- SMTP reputation, reverse DNS, DKIM, SPF, DMARC, queue handling, and abuse controls matter immediately for a public mail stack
- the existing monitoring stack is Grafana plus InfluxDB, not a standalone Prometheus deployment
- internal platform services need a stable submission path that does not depend on every caller knowing the internals of the mail stack

## Decision

We will standardize on a Dockerized mail platform built around Stalwart as the primary mail server, with a private mail gateway service in front of it for application-facing send and CRUD automation and a Brevo-backed fallback delivery path.

Primary runtime placement:

- host: `docker-runtime-lv3`
- stack root: `/opt/mail-platform`
- primary mail server: Stalwart
- private submission and CRUD facade: FastAPI mail gateway service
- backup resend provider: Brevo transactional email API

Primary responsibilities:

1. receive mail submitted by the platform over the private network
2. deliver outbound mail directly by MX when healthy
3. support future inbound mailbox delivery for LV3-managed domains
4. expose a durable management API for domains, principals, aliases, API keys, and queue-oriented operations
5. export enough telemetry to produce a dedicated Grafana dashboard
6. provide a fallback delivery path when primary local delivery attempts are failing

## Selected Architecture

### 1. Primary Mail Server

Stalwart will be the authoritative mail platform.

We choose it because the upstream project already combines the key capabilities this repository needs in one open-source server:

- Docker deployment
- SMTP plus mailbox protocols
- REST management API
- API-key based automation identities
- webhook support for real-time mail lifecycle events
- native Prometheus and OpenTelemetry telemetry exporters
- documented outbound failover routing rules

Initial Stalwart responsibilities should include:

- local domain and mailbox management
- SMTP submission for trusted internal clients
- SMTP delivery and queue management
- mailbox access protocols for future operational accounts
- webhook emission for message lifecycle events

### 2. Stable Local Submission Path

Platform services should not need to know Stalwart's management API or raw SMTP topology.

Instead, the platform exposes a private mail gateway API on `docker-runtime-lv3` that:

1. provides CRUD operations for domains and mailboxes
2. gives internal services and agents one stable send endpoint
3. centralizes sender policy, reply-to behavior, and fallback delivery routing
4. keeps future local-SMTP-first behavior available without changing callers

### 3. Backup Resend And Failover Delivery

Backup resend is defined as an automated secondary delivery path that is attempted after the preferred route fails, while preserving queued mail until either primary or secondary delivery succeeds or the message expires.

The implemented primary send path is:

- local applications and agents -> private mail gateway API -> Brevo transactional delivery

The implemented local receive path is:

- external senders -> `mail.lv3.org` -> Stalwart -> `server@lv3.org`

The gateway also retains a local SMTP submission path to Stalwart for future direct local-first delivery, but the first live implementation intentionally forces the Brevo fallback path until sender verification and deliverability policy are known-good.

The secondary delivery target is therefore explicit and repo-managed:

1. the gateway owns fallback resend policy
2. Brevo provides the backup resend provider for real delivery when the local address fails or when direct SMTP is not the chosen send path
3. sender identity, domain authentication, and fallback routing remain centralized instead of being spread across callers

## CRUD And Automation Model

The mail platform must support both human operators and machine actors.

We will use Stalwart's REST Management API as the system of record for automation-facing CRUD operations.

Expected machine-managed object types include:

- domains
- user accounts and service principals
- aliases and routing rules
- API keys for applications and automation agents
- queue and delivery inspection objects exposed by the platform

The repository should treat API identities as scoped automation credentials, not shared administrator secrets.

That implies:

- separate API keys for platform services, operator automation, and agent automation
- role or permission boundaries that keep agents away from broad mail-server administration unless explicitly required
- repo-managed secret references and preflight checks before any live converge

If future application requirements need a narrower domain-specific facade than the raw Stalwart API, that should be added as a thin internal service in front of Stalwart rather than replacing Stalwart as the control plane.

## Observability And Grafana Model

The platform will have a dedicated Grafana dashboard page for mail operations.

The dashboard must cover at least:

1. messages accepted for local submission
2. messages received from external senders
3. successful deliveries
4. temporary failures and permanent failures
5. queue depth and oldest queued message age
6. authentication failures and rejection rates
7. spam or policy rejection counts
8. fallback relay activation counts
9. SMTP session volume and error rates
10. storage pressure for mail data paths

The existing monitoring architecture matters here.

Because the repository currently uses InfluxDB-backed Grafana, the implementation should not assume a new standalone Prometheus server. Instead:

- Stalwart's Prometheus endpoint should be scraped locally and forwarded into the existing monitoring pipeline
- Stalwart webhooks should be used to capture message lifecycle events that are more useful as mail-flow counters than as raw infrastructure metrics
- Grafana should present both infrastructure health and mail-flow health on one dedicated dashboard

This split is deliberate:

- metrics answer whether the service is healthy
- webhooks and event ingestion answer what happened to the mail

## Placement And Network Model

The mail platform belongs on `docker-runtime-lv3`, not on the Proxmox host.

Public exposure should be split by protocol:

- HTTPS administration or self-service endpoints should remain behind the established NGINX edge publication model
- SMTP-related ports require explicit host firewall and NAT policy rather than trying to tunnel mail protocols through the HTTP edge

The first implementation should therefore keep these concerns separate:

1. Docker runtime stack convergence
2. mail DNS and reverse DNS
3. SMTP port exposure and firewall policy
4. Grafana integration

This avoids repeating the anti-pattern of mixing runtime, ingress, and observability in one opaque step.

## Alternatives Considered

### Option A: Stalwart

Why it fits:

- upstream documents a Docker deployment path
- the internal directory can be managed directly through the platform
- account management is available through the web admin and REST API
- API keys are first-class principals for management API access
- telemetry includes both Prometheus metrics and webhooks
- outbound routing explicitly supports relay routes and failover after retry thresholds

Why it is selected:

- it is the best match for "Dockerized mail server plus CRUD API plus Grafana-ready telemetry plus failover delivery" without needing several loosely integrated side projects

### Option B: Mailu

Why it was considered:

- upstream positions it as a full-featured Docker-based mail server
- it now exposes a RESTful API that can automate what the web administration interface can configure
- it is active and still releasing

Why it is not the primary choice:

- the upstream monitoring story is still mostly Docker logs rather than a native, rich metrics model
- it can satisfy administration requirements, but it leaves more observability assembly work to us than Stalwart does

### Option C: Postal

Why it was considered:

- it has strong HTTP API support for sending mail
- it exposes Prometheus-format metrics and webhooks
- it is well aligned with application-oriented outbound mail delivery

Why it is not the primary choice:

- upstream positions it as a mail delivery platform for websites and web servers, not as the general-purpose mailbox platform we want long term
- the current HTTP API explicitly does not manage all functions of the platform
- it is a strong outbound component, but a weaker fit for "one mail platform for send, receive, manage, and observe"

## Consequences

### Positive

- the platform gets one clear open-source mail architecture instead of an ad hoc notification path
- agents and server-side automation can use a real management API rather than undocumented UI operations
- Grafana can gain a first-class mail operations dashboard instead of hiding mail state in generic logs
- fallback delivery becomes an explicit platform feature rather than an afterthought

### Negative

- the platform takes on the operational burden of running internet-facing mail correctly
- DNS, reverse DNS, reputation, TLS, abuse prevention, and queue hygiene become part of the normal operating surface
- the Docker runtime VM becomes host to another stateful service that must be backed up and restored intentionally
- observability work is not free; it requires message-event ingestion in addition to basic service metrics

## Implementation Requirements

The first implementation workstream should produce, at minimum:

1. a compose-managed Stalwart stack rooted under `/opt/mail-platform`
2. a private mail gateway API for internal callers on the LV3 private network
3. repo-managed configuration for primary and fallback delivery policy
4. scoped API credentials for operators, services, and agent automation
5. Grafana dashboard provisioning for mail telemetry
6. backup coverage for the mail data path and configuration path
7. a runbook for DNS, PTR, DKIM, SPF, DMARC, and verification flow

It must not claim routine production readiness until:

- direct outbound deliverability is verified against major providers
- the fallback relay path is exercised intentionally
- queue visibility is present in Grafana
- API permission boundaries are documented and tested
- restore steps for mail data and configuration are documented

## Sources

- [Stalwart Docker installation](https://stalw.art/docs/install/platform/docker)
- [Stalwart REST Management API overview](https://stalw.art/docs/api/management/overview)
- [Stalwart API key principals](https://stalw.art/docs/auth/principals/api-key/)
- [Stalwart internal directory and account management](https://stalw.art/docs/auth/backend/internal)
- [Stalwart Prometheus metrics](https://stalw.art/docs/telemetry/metrics/prometheus/)
- [Stalwart webhooks](https://stalw.art/docs/telemetry/webhooks)
- [Stalwart outbound routing and failover delivery](https://stalw.art/docs/mta/outbound/routing/)
- [Mailu RESTful API](https://mailu.io/2.0/api.html)
- [Mailu maintenance and monitoring notes](https://mailu.io/2024.06/maintain.html)
- [Mailu releases](https://github.com/Mailu/Mailu/releases)
- [Postal API](https://docs.postalserver.io/developer/api)
- [Postal receiving by HTTP](https://docs.postalserver.io/developer/http-payloads/)
- [Postal health and Prometheus metrics](https://docs.postalserver.io/features/health-metrics/)
- [Postal releases](https://github.com/postalserver/postal/releases)
- [Stalwart GitHub repository and releases](https://github.com/stalwartlabs/stalwart)
