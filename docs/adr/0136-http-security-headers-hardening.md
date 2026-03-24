# ADR 0136: HTTP Security Headers Hardening

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.129.0
- Implemented In Platform Version: n/a
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The nginx edge (ADR 0021) serves every public and authenticated portal subdomain. TLS termination, reverse proxying, OAuth2-proxy integration, and WebSocket upgrades already work, but the shared edge configuration did not enforce a consistent browser hardening baseline across the published surfaces.

Without that baseline:

- browsers were not pinned to HTTPS with HSTS
- browsers could MIME-sniff responses without `X-Content-Type-Options`
- clickjacking protection depended on whatever an upstream application happened to emit
- CSP enforcement was absent at the edge even though public applications have very different client-side requirements
- referrer leakage and hardware API access were not constrained consistently
- crawler policy was only partially applied through ad hoc `X-Robots-Tag` rules

The result was uneven browser-side protection. Some upstream apps set their own headers, some did not, and several already emitted conflicting values. The edge needed to become the canonical policy enforcement point.

## Decision

We standardise HTTP security headers in the `nginx_edge_publication` role and make the edge authoritative for those headers on every published hostname.

### Global policy

The shared edge now adds the following headers on every published hostname:

- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- `Cross-Origin-Resource-Policy: same-origin`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()`
- `X-Robots-Tag: noindex, nofollow`

### Host-specific CSP overrides

The edge keeps one default CSP and uses explicit per-host overrides for public applications that need broader browser capabilities:

- `docs.lv3.org`: allows inline bootstrap scripts plus Google Fonts
- `grafana.lv3.org`: allows inline scripts, `unsafe-eval`, and blob workers required by Grafana
- `ops.lv3.org`: allows the external `unpkg.com` htmx asset plus inline bootstrap code
- `sso.lv3.org`: allows inline Keycloak login scripts and styles
- `uptime.lv3.org` and `status.lv3.org`: allow inline bootstrap code and WebSocket connectivity
- `api.lv3.org`: uses a locked-down `default-src 'none'` policy because it serves API responses, not an application UI

All CSP relaxations are declared in repo-managed role defaults so they can be audited and reviewed alongside the edge template.

### Edge-owned header values

For proxied applications, the nginx edge hides upstream `Strict-Transport-Security`, `Cross-Origin-Resource-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`, and `X-Robots-Tag` headers before adding the shared edge policy. This prevents conflicting duplicate values from upstream apps such as Keycloak, Grafana, and Uptime Kuma.

### Verification

The repository now ships `scripts/security_headers_audit.py` and `make security-headers-audit`. The audit derives the published hostnames from repo-managed topology, loads the expected edge header policy from the role defaults, and verifies live HTTPS responses for the required headers and host-specific CSP values.

## Consequences

**Positive**

- browser-facing protections are now consistent across all published subdomains
- CSP exceptions are explicit and bounded to the hostnames that need them
- upstream application defaults no longer override or conflict with the public edge policy
- header verification is repeatable from repo state instead of relying on one-off curls

**Negative / Trade-offs**

- some public applications still require weaker CSP directives such as `unsafe-inline` or `unsafe-eval`
- HSTS `preload` is a deliberate long-lived commitment for `lv3.org`
- `X-Frame-Options: DENY` will block future iframe embeddings unless they are deliberately re-scoped

## Boundaries

- This ADR governs browser-facing HTTP responses served through the nginx edge.
- It does not replace deeper public-surface scanning such as TLS posture checks or auth-bypass probes.
- API responses may still add their own application-specific headers, but the edge is the source of truth for the standard browser-hardening set above.

## Related ADRs

- ADR 0021: nginx edge publication
- ADR 0031: repository validation pipeline
- ADR 0092: platform API gateway
- ADR 0133: portal authentication by default
- ADR 0142: public surface automated security scan
