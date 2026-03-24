# ADR 0140: Grafana Public Access Hardening

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.123.1
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

Grafana is published at `https://grafana.lv3.org` for operator use, but its public surface needed tighter guardrails than "the dashboard URL redirects to login today".

The platform already uses Grafana's Keycloak OIDC login flow, yet three specific risks remained:

- the repo did not explicitly disable Grafana's public dashboard sharing feature
- the public edge still exposed `GET /api/health`, which returned Grafana's exact version and commit hash to unauthenticated callers
- there was no explicit repository verification proving that an unauthenticated caller could not reach a dashboard URL

The intended public status surface for outside observers is `https://status.lv3.org`, not Grafana itself.

## Decision

We will harden Grafana's public publication with repository-managed controls at both the Grafana runtime and the NGINX edge.

### Grafana runtime controls

Grafana will explicitly enforce:

- `auth.anonymous.enabled = false`
- `auth.disable_login_form = false` to preserve the managed recovery path
- `public_dashboards.enabled = false`
- `security.allow_embedding = false`

Grafana continues to use the repo-managed Keycloak OIDC login flow for authenticated operator access.

### Public edge controls

The NGINX edge publication for `grafana.lv3.org` will:

- return `404` for `/api/health` so version metadata is not exposed publicly
- strip `X-Grafana-Version` and `Via` from proxied responses
- mark the hostname `noindex`

### Verification contract

The monitoring role verification must prove all of the following:

- the managed dashboard still exists locally through the Grafana admin API
- an unauthenticated request to `/d/lv3-platform-overview/lv3-platform-overview` receives a redirect to `/login`
- the public `https://grafana.lv3.org/api/health` endpoint returns `404`
- the public login response headers do not expose `X-Grafana-Version` or `Via`

## Consequences

### Positive

- unauthenticated callers cannot inspect dashboard content through the normal dashboard URL path
- the public edge no longer discloses the live Grafana version through `/api/health`
- the public status use case stays isolated to `status.lv3.org`
- the hardening state is now explicit in repo automation instead of relying on current default behavior

### Negative / Trade-offs

- external tools that depended on `https://grafana.lv3.org/api/health` must switch to an authenticated path or a private health check
- public embeds and public dashboard share links are intentionally unsupported

## Boundaries

- This ADR hardens Grafana's public surface. It does not redesign dashboards, alerts, or the broader observability stack.
- This ADR does not make Grafana a public status page; that remains the role of ADR 0109's status service.

## Related ADRs

- ADR 0011: Initial monitoring and Grafana publication
- ADR 0056: Keycloak-backed SSO for shared control-plane services
- ADR 0109: Public status page
