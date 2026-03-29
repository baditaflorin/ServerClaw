# ADR 0280: Changedetection.io For External Content And API Change Monitoring

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform has strong internal availability monitoring:

- **Uptime Kuma** monitors HTTP status codes and response latency for known
  endpoints
- **Blackbox exporter** with Prometheus rules fires alerts on probe failures
- **ntopng** observes network flow patterns at the host level

None of these monitor *content changes* on external resources that the
platform depends on or tracks:

- upstream vendor documentation pages for services deployed on the platform
  (Proxmox release notes, Debian security advisories, Coolify changelogs)
- external JSON or YAML API responses that the platform consumes (Hetzner DNS
  API schemas, upstream container registry manifests)
- dependency version feeds such as GitHub release pages for self-hosted
  software
- external security advisory feeds for components without a formal CVE RSS

When upstream content changes, operators currently discover it by chance or
by manually checking pages during maintenance windows. There is no systematic
watch that fires an ntfy or Mattermost notification when a watched page or
API response changes.

Changedetection.io is a CPU-only, open-source service that polls URLs on a
configurable schedule, diffs the response, and fires notifications over any
configured channel.

## Decision

We will deploy **Changedetection.io** as the external content and API change
monitoring service.

### Deployment rules

- Changedetection.io runs as a Docker Compose service on the docker-runtime VM
- It is internal-only; no public subdomain is issued
- State (watched URLs and diff history) is stored on a named Docker volume
  included in the backup scope (ADR 0086)
- Notifications are routed through Ntfy (ADR 0124) and Mattermost for
  consistency with the platform's existing alert channels
- No secrets are required for basic operation; authenticated watch targets
  store credentials in OpenBao (ADR 0077)

### Watch catalogue governance

- all watched URLs are declared in the Ansible role's `defaults/main.yml` as
  a list; ad-hoc UI-only additions are treated as drift and reconciled on the
  next converge
- each watch entry records the URL, check interval, notification channel, and
  the reason it is being watched
- watches are grouped by purpose: `upstream-releases`, `security-advisories`,
  `dependency-feeds`, `api-schemas`

### Notification rules

- a content change on a `security-advisories` watch fires an immediate ntfy
  push notification at high priority
- a content change on an `upstream-releases` watch fires a Mattermost message
  in the platform-ops channel
- checks are spaced at a minimum of one hour to avoid being blocked by
  upstream rate limits

## Consequences

**Positive**

- Upstream release and security advisory changes are caught systematically
  without operator polling.
- The declared watch catalogue is version-controlled in the Ansible role and
  auditable.
- Content diffing gives operators a precise view of what changed, not just
  that something changed.
- The service operates entirely on CPU with negligible resource consumption at
  the polling intervals used.

**Negative / Trade-offs**

- External pages behind bot-detection or aggressive rate limiting may require
  browser-mode rendering (Playwright), which adds resource overhead; those
  watches should be flagged explicitly.
- Content change does not mean actionable change; some pages change layout or
  cookie notices without substantive content updates, requiring watch
  selectors to be tuned.

## Boundaries

- Changedetection.io monitors external URLs only; internal endpoint
  availability remains with Uptime Kuma and the Blackbox exporter.
- It does not replace Trivy or the vulnerability budget framework (ADR 0269)
  for CVE tracking against deployed images.
- It is not a web scraping pipeline; it watches for change signals, not for
  data extraction at scale.

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0096: SLO probes and Blackbox exporter
- ADR 0124: Ntfy for push notifications
- ADR 0142: Public surface security scanning
- ADR 0269: Vulnerability budgets and image host freshness promotion gates

## References

- <https://changedetection.io/docs/>
