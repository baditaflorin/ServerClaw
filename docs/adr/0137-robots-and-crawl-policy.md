# ADR 0137: Robots.txt and Crawl Policy

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.126.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-25

## Context

The shared NGINX edge already publishes multiple `lv3.org` hostnames, but crawl controls were inconsistent:

- `robots.txt` was not served on the published edge hostnames.
- `X-Robots-Tag` was only applied to selected static surfaces instead of being global.
- repository-generated HTML surfaces did not consistently emit a robots meta tag.
- the `lv3.org` apex already resolved to the shared public IP, but the edge certificate did not cover the apex hostname.

That combination allowed search engines and passive indexing systems to discover login pages, informational landing pages, and URL structure that are not intended to appear in public search results.

## Decision

The platform will apply one crawl policy across the entire public edge:

- serve the same `robots.txt` on `lv3.org` and every edge-published `*.lv3.org` hostname
- send `X-Robots-Tag: noindex, nofollow` on every NGINX edge response
- emit `<meta name="robots" content="noindex, nofollow">` on repository-generated HTML surfaces that the edge serves directly
- include `lv3.org` in the shared edge certificate set so the apex crawl-policy endpoint is valid over HTTPS

The shared `robots.txt` body is:

```txt
User-agent: *
Disallow: /

# This domain is a private homelab infrastructure platform.
# There is no public content intended for indexing.
```

## Implementation

The repository implementation is carried by:

- `roles/nginx_edge_publication/` and the mirrored collection role copy, which now render the shared `robots.txt`, add the global `X-Robots-Tag`, publish an explicit `lv3.org` vhost, and verify the header and content locally on the edge VM
- `inventory/group_vars/platform.yml`, which now manages the apex `A` record alongside the published subdomains
- `config/certificate-catalog.json`, which now inventories the apex edge certificate endpoint
- `scripts/portal_utils.py`, `mkdocs.yml`, and the theme override under `docs/theme-overrides/`, which now add robots meta tags to generated HTML portals
- `docs/runbooks/configure-edge-publication.md` and `docs/runbooks/developer-portal.md`, which now document the crawl-policy verification steps

## Consequences

### Positive

- search engines that respect `robots.txt` and `X-Robots-Tag` stop indexing the public edge surfaces
- the crawl policy is simple and uniform instead of being tied to per-site exceptions
- apex HTTPS now has a valid repository-defined path instead of resolving to a certificate mismatch

### Negative / Trade-offs

- `robots.txt`, `X-Robots-Tag`, and robots meta tags are advisory; they do not block hostile scanners
- the live platform remains unchanged until the public-edge and DNS automation is applied from `main`

## Boundaries

- This ADR governs crawl policy for HTTP(S) content on the shared NGINX edge.
- It does not replace authentication, firewall policy, or rate limiting.
- It does not cover SMTP, MX, SPF, DKIM, or other DNS-discoverable metadata outside the HTTP surface.

## Related ADRs

- ADR 0015: lv3.org DNS and subdomain model
- ADR 0021: Shared NGINX edge publication
- ADR 0076: Subdomain governance and DNS lifecycle
- ADR 0101: Automated certificate lifecycle management
