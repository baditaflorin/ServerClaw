# ADR 0137: Robots.txt and Search Engine Crawl Policy

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

No `robots.txt` file is currently served on any `lv3.org` subdomain. The nginx edge serves `X-Robots-Tag: noindex` on informational static pages, but this header is missing from all other subdomains.

The consequence is that web crawlers — including Googlebot, Bingbot, but also vulnerability scanners and dark-web indexers like Shodan and Censys — may crawl and index:

- The Keycloak login pages at `sso.lv3.org`, exposing the Keycloak version string and login endpoint structure.
- The Grafana landing page at `grafana.lv3.org`, exposing the Grafana version and any unauthenticated panel URLs.
- The Uptime Kuma dashboard at `uptime.lv3.org`, exposing service names and their historical availability data.
- The static informational pages at `build.lv3.org`, `docker.lv3.org`, etc., which may appear in search results and confirm that the subdomain pattern is `*.lv3.org`.

Version strings in HTTP headers or login pages are indexed by Shodan and CVE-correlated scanners. A publicly indexed Keycloak version string combined with a known CVE creates a direct attack vector.

The correct policy is:
- **Internal portals**: `noindex, nofollow` (authenticated; search engines should never reach content, but the header prevents accidental indexing of the login page structure).
- **Public informational pages**: `noindex, nofollow` (no value in indexing "this service is private").
- **Public API/SSO**: `noindex, nofollow` (machine-to-machine; not useful in search results).
- **Nothing on this domain is intended to be indexed**.

## Decision

We will serve a `robots.txt` at the apex domain and on every subdomain that disallows all crawlers from all paths, and add `X-Robots-Tag: noindex, nofollow` to every nginx vhost response.

### Apex domain robots.txt

Served at `https://lv3.org/robots.txt` and at `https://*.lv3.org/robots.txt` (via a catch-all nginx location block):

```txt
User-agent: *
Disallow: /

# This domain is a private homelab infrastructure platform.
# There is no public content intended for indexing.
# If you are a security researcher and believe you have found
# a vulnerability, please contact the owner directly.
```

### Per-subdomain nginx configuration

```nginx
# Added to every server block via the nginx_edge_publication Ansible role
location = /robots.txt {
    add_header Content-Type text/plain;
    add_header X-Robots-Tag "noindex, nofollow" always;
    return 200 "User-agent: *\nDisallow: /\n";
}

# Applied to all responses (reinforces HTTP header)
add_header X-Robots-Tag "noindex, nofollow" always;
```

### Keycloak version string suppression

Keycloak's login page includes version metadata in HTTP headers and in the HTML source. The nginx proxy for `sso.lv3.org` will strip version-revealing headers before passing responses to clients:

```nginx
# In the sso.lv3.org vhost
proxy_hide_header X-Powered-By;
proxy_hide_header Server;
proxy_hide_header X-Keycloak-Version;

# Replace the Server header with a non-revealing value
add_header Server "lv3-edge" always;
```

Similarly, Grafana's `X-Grafana-Version` and Windmill's `X-Windmill-Version` headers are stripped at the proxy layer.

### Shodan/Censys re-scan request

After deploying these changes, the operator should request a re-index from Shodan and Censys using their respective "remove from index" tools, ensuring that any previously cached version information is removed.

### Monitoring

The weekly `validate-security-headers` workflow (ADR 0136) also checks that:
- `GET /robots.txt` returns 200 with `Disallow: /`.
- `X-Robots-Tag: noindex` is present on all subdomain responses.
- The `Server` header does not expose application version strings.

## Consequences

**Positive**

- Web crawlers and vulnerability scanners that respect `robots.txt` (which includes most major search engines and Shodan) will not index the platform's subdomains.
- Stripping version strings from proxy headers eliminates the easiest vector for CVE correlation against the live platform.
- The consistent policy ("nothing on this domain is indexed") is simple to reason about and maintain.

**Negative / Trade-offs**

- `robots.txt` and `X-Robots-Tag` are advisory; malicious scanners ignore them. This ADR provides protection against accidental indexing, not against determined adversarial scanning. The latter requires firewall-level controls (ADR 0067) and rate limiting.
- Stripping the `Server` header does not prevent fingerprinting by response timing, default error page format, or HTTP/2 settings. Determined fingerprinting is still possible; this ADR reduces low-effort fingerprinting.

## Boundaries

- This ADR covers crawl policy for web content served by nginx. It does not govern SMTP MX records, SPF/DKIM/DMARC records, or other DNS-discoverable metadata.
- Robots.txt is advisory. This ADR does not replace proper access controls (ADR 0133) or firewall rules (ADR 0067).

## Related ADRs

- ADR 0021: nginx edge publication (nginx template modifications)
- ADR 0056: Keycloak SSO (version string suppression on sso.lv3.org)
- ADR 0133: Portal authentication by default (access control; this ADR covers crawl policy)
- ADR 0136: HTTP security headers hardening (X-Robots-Tag complement to robots.txt)
- ADR 0139: Subdomain exposure audit (validates robots.txt presence)
- ADR 0142: Public surface penetration testing (checks robots.txt, version strings)
