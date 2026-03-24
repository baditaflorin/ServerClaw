# ADR 0136: HTTP Security Headers Hardening

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The nginx edge (ADR 0021) serves all public and authenticated portal subdomains. The current nginx configuration handles TLS termination, reverse proxying, OAuth2-proxy integration, and WebSocket upgrades correctly. However, it is missing a set of standard HTTP security headers that provide browser-level protection against common web vulnerabilities:

- **No `Strict-Transport-Security` (HSTS)**: browsers are not told to always use HTTPS, leaving users vulnerable to SSL stripping on first visit.
- **No `Content-Security-Policy` (CSP)**: browsers will execute any JavaScript injected via XSS, including scripts from arbitrary external origins.
- **No `X-Frame-Options`**: portals can be embedded in iframes on attacker-controlled pages (clickjacking).
- **No `X-Content-Type-Options`**: browsers may MIME-sniff responses and execute content as a different type than declared.
- **No `Referrer-Policy`**: the full URL (including path and query parameters, which may contain session tokens) is sent in the `Referer` header to any external resource.
- **No `Permissions-Policy`**: browsers can access camera, microphone, and geolocation without restriction.

The consequence is that even with correctly enforced authentication, an XSS vulnerability in a portal (e.g., a Grafana plugin, a Windmill script output, or a changelog entry that renders unsanitised HTML) would have no browser-level containment.

## Decision

We will add a standardised set of HTTP security headers to the nginx edge template, applied globally with per-subdomain override capability.

### Global header block

```nginx
# Added to the `http {}` block in /etc/nginx/nginx.conf
# (via the nginx_edge_publication Ansible role)

map $request_uri $csp_policy {
    default "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
}

add_header Strict-Transport-Security   "max-age=63072000; includeSubDomains; preload" always;
add_header X-Content-Type-Options      "nosniff" always;
add_header X-Frame-Options             "DENY" always;
add_header Referrer-Policy             "strict-origin-when-cross-origin" always;
add_header Permissions-Policy          "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()" always;
add_header Content-Security-Policy     $csp_policy always;
add_header X-Robots-Tag                "noindex, nofollow" always;
```

### Per-subdomain CSP overrides

Different portals have different JavaScript requirements. The global CSP above is strict (no inline scripts, no external origins). Portals that require relaxed CSP must declare an override in the Ansible role vars:

```yaml
# In the nginx_edge_publication role, per-vhost config:

vhosts:
  - subdomain: grafana
    csp_override: "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' wss://grafana.lv3.org"
    # Grafana requires unsafe-eval for its panel rendering; this is a known Grafana limitation

  - subdomain: windmill
    csp_override: "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; worker-src blob:; connect-src 'self' wss://windmill.lv3.org"
    # Windmill uses dynamic script execution for workflow editor

  - subdomain: ops
    # Uses default strict CSP — ops portal is a controlled static+htmx app
```

All CSP overrides must be declared in the role configuration. Undeclared `unsafe-*` directives cause the validation pipeline (ADR 0031) to emit a warning requiring justification.

### HSTS preload

The `Strict-Transport-Security` header includes `preload`. This means the domain will be submitted to the HSTS preload list, ensuring browsers never make an HTTP request to `*.lv3.org` even on first visit. This is a one-time, permanent decision: once a domain is on the preload list, removing it takes months. The decision to include `preload` is deliberate and appropriate for a homelab where all subdomains are operator-facing.

### `X-Robots-Tag` for all portals

All authenticated portals (`changelog.lv3.org`, `docs.lv3.org`, `ops.lv3.org`, `grafana.lv3.org`, `windmill.lv3.org`) include `X-Robots-Tag: noindex, nofollow` to prevent search engine crawling and indexing. This is complementary to authentication: even if a search engine somehow reaches the login page, it will not index the URL structure.

### Security header validation

A weekly Windmill workflow `validate-security-headers` makes HTTP requests (without auth) to each public-facing subdomain and checks for the presence and correct values of all required headers. Failures are written to the mutation ledger and posted to Mattermost `#platform-security`.

```bash
$ lv3 run validate-security-headers
changelog.lv3.org:  ✓ HSTS  ✓ CSP  ✓ X-Frame  ✓ X-Content-Type  ✓ Referrer  ✓ Robots
docs.lv3.org:       ✓ HSTS  ✓ CSP  ✓ X-Frame  ✓ X-Content-Type  ✓ Referrer  ✓ Robots
grafana.lv3.org:    ✓ HSTS  ✓ CSP* ✓ X-Frame  ✓ X-Content-Type  ✓ Referrer  ✓ Robots
                           * CSP override: unsafe-eval (justified: Grafana panel rendering)
```

## Consequences

**Positive**

- XSS vulnerabilities in any portal now have browser-level containment: scripts can only load from `'self'`, frames cannot embed the portal, and MIME sniffing is disabled.
- HSTS ensures all portal traffic is always encrypted, even for users who type the hostname without a scheme.
- The weekly header validation workflow provides continuous assurance that the headers are present and correct even after nginx config changes.

**Negative / Trade-offs**

- Some third-party apps (Grafana, Windmill) require CSP relaxations (`unsafe-eval`). These relaxations must be documented and justified; they create a weaker protection surface for those portals. The correct long-term fix is upstream (replacing apps that require `unsafe-eval`), not a workaround here.
- HSTS `preload` is irreversible once submitted. The domain cannot be removed from the preload list quickly if the homelab is decommissioned or the domain changes. This is an acceptable risk for a stable homelab domain.
- `X-Frame-Options: DENY` will break any iframe embedding of portal content. If any current or future integration embeds a portal in a dashboard (e.g., an iframe in a homepage service dashboard), it will need to use the `SAMEORIGIN` variant.

## Boundaries

- This ADR governs headers on the nginx edge. Applications that serve their own API responses (the platform API gateway, ADR 0092) are responsible for their own headers on JSON responses; those do not need CSP but should include `X-Content-Type-Options` and `X-Robots-Tag`.
- The Permissions-Policy header denies hardware APIs but does not restrict JavaScript permissions; those are governed by CSP.

## Related ADRs

- ADR 0021: nginx edge publication (template where headers are added)
- ADR 0031: Repository validation pipeline (CSP override justification checks)
- ADR 0049: Private-first API publication (API gateway headers)
- ADR 0133: Portal authentication by default (authentication; this ADR covers browser hardening)
- ADR 0137: Robots.txt and crawl policy (companion to X-Robots-Tag)
- ADR 0142: Public surface penetration testing (validates headers are present)
