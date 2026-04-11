# ADR 0368: Nomad OIDC Auth and Edge Publication

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not applicable
- Implemented In Platform Version: not applicable
- Implemented On: not applicable
- Date: 2026-04-05
- Tags: nomad, oidc, keycloak, edge, sso, scheduler

## Context

The Nomad scheduler (ADR 0232) was deployed as a private-only service accessible
through the Tailscale TCP proxy at `100.64.0.1:8013`. The UI displayed "Not
Authorized" because no OIDC auth method was configured, and the management
bootstrap token was the only credential. This blocked platform operators from
inspecting jobs via the browser and prevented agents from being aware of Nomad.

## Decision

### Edge publication at scheduler.example.com

Publish the Nomad UI on the public edge at `scheduler.example.com` without
oauth2-proxy, using Nomad's native OIDC auth method instead.

Nomad requires its own ACL tokens for every API call — oauth2-proxy cannot
provide these. Wrapping the UI in both oauth2-proxy and Nomad OIDC would force a
double-login UX. This is the same pattern as `sso.example.com` (Keycloak), which is
edge-published but handles its own authentication.

### Keycloak OIDC client

A confidential Keycloak client `nomad` provides the OIDC integration:
- Standard flow with group membership mapper
- Redirect URIs: `https://scheduler.example.com/ui/settings/tokens`, `http://localhost:4649/oidc/callback`

### Nomad ACL configuration

- OIDC auth method `keycloak` set as default (UI shows "Sign In with OIDC" button)
- ACL policy `platform-admin`: full write across all namespaces, nodes, agents
- ACL policy `platform-reader`: read-only across all namespaces and nodes
- Binding rule: `lv3-platform-admins` group maps to `platform-admin` role
- Default binding: any authenticated user maps to `platform-reader` role

### HTTPS upstream proxy

The NGINX edge proxies to Nomad's HTTPS endpoint with `proxy_ssl_verify off`
because Nomad uses a private CA. A new `upstream_ssl_verify` field was added to
the service topology edge configuration and the NGINX template.

### Agent toolchain integration

Three agent tools added: `list-nomad-jobs`, `get-nomad-job-status`,
`dispatch-nomad-job`. Documented in AGENTS.md so all future agent sessions are
aware of the Nomad scheduler.

## Consequences

### Positive

- Platform operators can sign into Nomad via Keycloak with a single click
- Agents can list and dispatch Nomad jobs through the tool registry
- Job status is visible in a browser at `scheduler.example.com`
- OIDC auth provides user-level audit trail in Nomad's ACL logs

### Negative / Trade-offs

- Nomad UI is exposed on the public internet (mitigated by OIDC auth requirement)
- The `proxy_ssl_verify off` directive reduces TLS assurance on the edge-to-Nomad
  path (acceptable for LAN-only traffic)

## Related ADRs

- ADR 0232: Nomad for durable batch and long-running internal jobs
- ADR 0056: Keycloak SSO
- ADR 0063: Keycloak SSO for internal services
- ADR 0069: Agent tool registry and governed tool calls
- ADR 0133: Operator-facing publications authenticated by default
