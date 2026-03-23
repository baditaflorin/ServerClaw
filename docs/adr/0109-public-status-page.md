# ADR 0109: Public Status Page

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

The platform publishes several services to the public internet: `grafana.lv3.org`, `sso.lv3.org`, `uptime.lv3.org`, `ops.lv3.org`, and `docs.lv3.org`. External users — collaborators, link recipients, anyone who was given a URL — have no way to determine whether a service is currently experiencing an outage or whether their inability to reach it is on their end.

Uptime Kuma (ADR 0027) already monitors all published services internally. It has a built-in status page feature that publicly exposes a subset of its monitoring data without requiring authentication. This feature has not been configured.

The absence of a public status page also creates an operational blind spot: if the platform's own internal monitoring is down (monitoring VM failure), an operator outside the network has no signal about platform health. A truly external status check — one that does not depend on internal platform services — provides a last-resort signal.

An external status page has a second benefit: it signals that the platform is a product. A product tells its users when it is down. A collection of services does not.

## Decision

We will configure Uptime Kuma's built-in status page at `status.lv3.org` and supplement it with an external synthetic monitoring probe via Uptime Robot (free tier) for last-resort monitoring independence.

### Uptime Kuma status page configuration

Uptime Kuma supports multiple status pages, each showing a configurable subset of monitors. We create one public status page:

**Page configuration** (via Uptime Kuma API or Ansible role):

```yaml
status_page:
  slug: lv3-platform
  title: "lv3 Platform Status"
  description: "Current operational status of lv3.org platform services"
  theme: dark
  show_tags: false
  custom_css: ""
  footer_text: "lv3.org — powered by Uptime Kuma"

monitors_included:
  - name: "SSO (Keycloak)"
    url: "https://sso.lv3.org/health/ready"
    group: "Platform Services"

  - name: "Grafana"
    url: "https://grafana.lv3.org/api/health"
    group: "Observability"

  - name: "Ops Portal"
    url: "https://ops.lv3.org/health"
    group: "Platform Services"

  - name: "Uptime Monitor"
    url: "https://uptime.lv3.org"
    group: "Platform Services"

  - name: "API Gateway"
    url: "https://api.lv3.org/v1/health"
    group: "Platform Services"

  - name: "Documentation"
    url: "https://docs.lv3.org"
    group: "Platform Services"
```

Monitors that are internal-only (Postgres, OpenBao, step-ca, Windmill) are explicitly excluded from the public status page. The public page shows only what is meaningful to an external user.

### Subdomain and DNS

`status.lv3.org` is registered in `config/subdomain-catalog.json` as a public subdomain. The DNS record points to `10.10.10.10` (nginx-lv3). The nginx edge proxies to `uptime-kuma:3001` (Uptime Kuma's status page endpoint), without OIDC protection — it is deliberately public.

```nginx
# nginx config for status.lv3.org
server {
    listen 443 ssl;
    server_name status.lv3.org;

    location / {
        proxy_pass http://10.10.10.20:3001;
        proxy_set_header Host $host;
        # No auth_request — this is a public page
    }
}
```

### Incident announcements

The status page supports manual incident announcements via the Uptime Kuma API. The maintenance window workflow (ADR 0080) is updated to post a maintenance announcement to the status page when a maintenance window is declared:

```python
def post_status_page_maintenance(window: MaintenanceWindow):
    uptime_kuma_api.create_maintenance(
        title=f"Planned maintenance: {window.reason}",
        description=f"Services may be intermittently unavailable.",
        start_date=window.start,
        end_date=window.end,
        affected_monitors=resolve_affected_monitors(window.service)
    )
```

This creates a scheduled "Under Maintenance" status on the public page during the maintenance window, preventing user confusion.

### External synthetic monitoring (Uptime Robot)

Uptime Kuma monitoring runs on `monitoring-lv3`, which is itself part of the platform. If the Proxmox host fails entirely, Uptime Kuma stops monitoring and the status page goes dark — exactly when it is most needed.

We add **Uptime Robot** (free tier, 50 monitors, 5-minute intervals) as an independent external probe:

```
External monitors (Uptime Robot, free tier):
  - https://sso.lv3.org/health/ready   (keyword: "UP")
  - https://grafana.lv3.org/api/health (keyword: "ok")
  - https://status.lv3.org             (HTTP 200)
```

Uptime Robot sends email and Mattermost webhook alerts when external monitors fail. These alerts are independent of the internal Alertmanager (ADR 0097) — they work even when Alertmanager is down.

The Uptime Robot API key is stored in OpenBao (`platform/uptime-robot/api-key`) and the Mattermost webhook URL is configured as a notification integration.

### Status page SLO

The status page itself has an SLO (ADR 0096):

```json
{
  "id": "status-page-availability",
  "service": "status-page",
  "indicator": "uptime",
  "objective_percent": 99.9,
  "window_days": 30,
  "probe": "http_probe_success{job='uptime-kuma-status-page'}",
  "description": "The public status page is available 99.9% of the time"
}
```

The status page's SLO is held to a higher standard than most services because it is the last-resort signal for operators and users during an incident.

### Privacy

The public status page does not expose:
- Internal IP addresses
- VM names or topology
- Error messages from services (only up/down status)
- Service version numbers

The "Description" field for each monitor on the public page shows only the service name and category, not technical details.

## Consequences

**Positive**
- External users have a definitive answer to "is the platform down or is it just me?" without needing to contact the operator
- Maintenance windows create proactive status page announcements; planned downtime is not a surprise
- Uptime Robot provides monitoring independence from the internal platform; total platform failure is detectable from outside
- The status page signals that the platform is a product with defined availability commitments

**Negative / Trade-offs**
- The Uptime Robot free tier polls every 5 minutes; there is a 5-minute detection lag for external incidents. The internal Alertmanager has 2-minute polling; the external probe is for backup, not primary alerting
- Uptime Robot is a third-party SaaS service; adding a dependency on it for monitoring independence is a trade-off — but the alternative (no external monitoring) is worse
- The status page shows only binary up/down status; it does not show performance degradation (e.g., Keycloak is responding but slowly). Adding latency monitoring to Uptime Kuma would address this in a future iteration

## Alternatives Considered

- **Freshping / Better Uptime / Betterstack**: similar external synthetic monitoring services; Uptime Robot is chosen for its generous free tier and long track record
- **Self-hosted external probe on a separate server**: eliminates the SaaS dependency but requires a second server outside the platform — cost and complexity not justified
- **No external monitoring; just the internal Uptime Kuma page**: does not provide monitoring independence; if the platform is fully down, the status page is also down; this was the deciding factor for adding Uptime Robot

## Related ADRs

- ADR 0015: DNS and subdomain model (`status.lv3.org` DNS entry)
- ADR 0021: Public subdomain publication (nginx edge serves the status page)
- ADR 0027: Uptime Kuma (provides the status page backend)
- ADR 0076: Subdomain governance (`status.lv3.org` registration)
- ADR 0080: Maintenance window (creates status page announcements)
- ADR 0096: SLO definitions (status page has its own SLO)
- ADR 0097: Alerting routing (Uptime Robot alerts supplement Alertmanager)
