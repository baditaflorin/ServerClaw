# ADR 0133: Portal Authentication by Default

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.130.0
- Implemented In Platform Version: 0.114.7
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The platform publishes several browser-facing portals whose content is operationally sensitive even when the surfaces are read-only:

- `ops.lv3.org` exposes live platform state and operator workflows
- `changelog.lv3.org` exposes deployment history, actors, and promotion cadence
- `docs.lv3.org` exposes ADRs, runbooks, topology, and service reference material
- `grafana.lv3.org` exposes service names, health, capacity, and infrastructure telemetry

Treating these portals as public because they are "read-only" leaks operational context that an attacker can use for reconnaissance. The correct default is that portal access requires authentication unless a surface is deliberately carved out as public.

## Decision

We will enforce authentication by default for portal services.

### Portal policy

- `ops.lv3.org` requires Keycloak OIDC through the shared edge `oauth2-proxy`.
- `changelog.lv3.org` requires Keycloak OIDC through the shared edge `oauth2-proxy`.
- `docs.lv3.org` requires Keycloak OIDC through the shared edge `oauth2-proxy`, with read-only access for authenticated operators.
- `grafana.lv3.org` requires Keycloak-backed login and must not allow anonymous viewers.

### Repository contract

The canonical subdomain catalog now records an `auth_requirement`, `audience`, and optional `justification` for every hostname. The browser-facing default remains Keycloak OIDC; explicit public classifications must carry a written justification. Non-browser or private-only hostnames are also classified so the catalog remains honest for the full surface set.

The repository validates this contract with:

- schema enforcement in `docs/schema/subdomain-catalog.schema.json`
- base catalog validation in `scripts/subdomain_catalog.py`
- portal-policy validation in `scripts/validate_portal_auth.py`

### Edge implementation

The shared edge `oauth2-proxy` now issues a cookie for `.lv3.org`, allowing one Keycloak-backed browser session to protect `ops`, `docs`, and `changelog` through the common NGINX `auth_request` pattern already used for the operations portal.

## Consequences

### Positive

- Unauthenticated requests to the operator portals are blocked before any content is served.
- Portal access policy is explicit in version-controlled data instead of being inferred from ad hoc NGINX state.
- Future public exceptions require an intentional justification in the catalog.

### Negative

- Operators now need a Keycloak session to browse the docs or deployment history portals.
- Public sharing of internal screenshots or portal links becomes less convenient and must use screenshots or curated public surfaces instead.

## Verification

Repository validation must pass and the live platform must reject unauthenticated access:

- `https://ops.lv3.org/` returns a redirect to `/oauth2/sign_in`
- `https://changelog.lv3.org/` returns a redirect to `/oauth2/sign_in`
- `https://docs.lv3.org/` returns a redirect to `/oauth2/sign_in`
- `https://grafana.lv3.org/` does not serve dashboards anonymously

## Related ADRs

- ADR 0011: Monitoring VM with Grafana and Proxmox metrics
- ADR 0021: Public subdomain publication through the NGINX edge
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0074: Platform operations portal
- ADR 0081: Platform changelog and deployment history
- ADR 0094: Developer portal and documentation site
