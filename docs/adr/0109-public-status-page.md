# ADR 0109: Public Status Page

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.104.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

The platform already publishes several public hostnames, including `grafana.lv3.org`, `sso.lv3.org`, and `uptime.lv3.org`. External users still lacked one unauthenticated place to answer a simple question: is the platform down, or is the problem local to them?

Uptime Kuma already tracks the public surfaces, but its built-in public status-page feature was not configured. The maintenance-window workflow also had no outward-facing publication path, so planned downtime looked indistinguishable from an outage to anyone outside the private operator context.

There was also no independent last-resort signal. If the platform lost the Uptime Kuma runtime entirely, there would be no external confirmation that the public status surface itself had failed.

## Decision

We will publish a repo-managed public status page at `status.lv3.org`, backed by Uptime Kuma and supplemented by an independent Uptime Robot probe set.

### Public status page

The repository now defines one Uptime Kuma status page in `config/uptime-kuma/status-page.json`:

- slug: `lv3-platform`
- title: `lv3 Platform Status`
- hostname: `status.lv3.org`
- groups:
  - Platform Access: `Keycloak OIDC Discovery`, `Uptime Kuma Public`
  - Observability: `Grafana Public`, `NGINX Edge Public`

Only externally meaningful monitors are published. Private-only services such as Postgres, OpenBao, Windmill, and step-ca remain off the public page.

### Edge publication

`status.lv3.org` is registered in the canonical subdomain catalog and added to the shared NGINX edge topology. The edge keeps the hostname public and unauthenticated, but maps only the root request to the Uptime Kuma slug route so that the dedicated hostname serves the status page cleanly while still letting the backend load its normal assets.

### Maintenance-window publication

`scripts/maintenance_window_tool.py` now performs a best-effort Uptime Kuma sync when a maintenance window is opened or closed:

- open: create or update a matching single-run Uptime Kuma maintenance entry
- close: remove the matching Uptime Kuma maintenance entry
- monitor selection: derive the affected public monitor from the canonical service catalog, or all published status-page monitors for `maintenance/all`

This keeps ADR 0080 as the source of truth while exposing planned downtime on the public page.

### Independent monitoring

The repository now includes `scripts/uptime_robot_tool.py` plus the canonical config in `config/uptime-robot/public-status-monitoring.json` for three independent 5-minute monitors:

- `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration`
- `https://grafana.lv3.org/api/health`
- `https://status.lv3.org`

The same config also defines two alert contacts:

- operator email: `baditaflorin@gmail.com`
- Mattermost webhook: controller-local secret `uptime_robot_mattermost_webhook`

### SLO and health contract

The status page now has:

- a canonical health-probe contract in `config/health-probe-catalog.json`
- a canonical service entry in `config/service-capability-catalog.json`
- a status-page SLO stub in `config/slo-catalog.json`

The Uptime Kuma health-probe contract intentionally disables same-instance self-monitoring to avoid recursive checks. External status-page coverage is delegated to Uptime Robot.

## Consequences

### Positive

- External users get a stable public status surface at `status.lv3.org`
- Planned maintenance can be reflected on the public page from the same maintenance-window workflow that suppresses internal alert noise
- Independent external monitoring now exists for the public status surface and two critical public services
- The platform’s public-facing operational posture is more product-like and less ad hoc

### Negative / Trade-offs

- The independent probe path depends on a third-party SaaS
- Free-tier Uptime Robot polling remains coarse at 5 minutes
- The status-page SLO is currently a catalog contract only; full ADR 0096 rule generation is still separate work
- Maintenance publication is best-effort and does not block the primary ADR 0080 maintenance-window path if the Uptime Kuma admin session is unavailable

## Alternatives Considered

- No public status page: rejected because it leaves external users without a clear outage signal
- Public static page with manually edited incidents: rejected because Uptime Kuma already owns the live monitor state
- Self-hosting the independent probe elsewhere: rejected for now because the extra host and network path are not justified yet

## Related ADRs

- ADR 0015: DNS and subdomain model
- ADR 0021: Public subdomain publication
- ADR 0027: Uptime Kuma
- ADR 0076: Subdomain governance
- ADR 0080: Maintenance window
- ADR 0096: SLO definitions
- ADR 0097: Alert routing
