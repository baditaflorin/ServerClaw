# ADR 0444: nginx Buffer Sizing for oauth2-proxy Subrequest and Callback

- Status: Accepted
- Implementation Status: Implemented — `proxy_buffer_size 64k` on both `/oauth2/auth` and `/oauth2/callback` locations in `lv3-edge.conf.j2`
- Date: 2026-04-28
- Concern: edge-availability, oidc-resilience, header-overflow, debuggability
- Tags: nginx, oauth2-proxy, keycloak, buffer-sizing, header-overflow
- Depends on:
  - ADR 0021 (Public subdomain publication at the nginx edge)
  - ADR 0248 (Session and logout authority across Keycloak, oauth2-proxy, and apps)
- Supersedes: the v0.179.2 hot-fix (16k on `/oauth2/callback` only)

---

## Context

Two production outages within twelve hours, both manifesting as
`500 Internal Server Error` from nginx on OIDC-protected sites
(`ops.<domain>`, `grafana.<domain>`, `tasks.<domain>`, …).

### Outage 1 — `/oauth2/callback` overflow (fixed in v0.179.2)

After a successful Keycloak OIDC login, oauth2-proxy responds to the
public callback with a `Set-Cookie` header that contains the full JWT
access token plus the refresh token. With Keycloak group-membership
claims included, that cookie is 8–12 KB. nginx's default
`proxy_buffer_size` (4 KB / one OS page) is too small to hold the
response header, so nginx aborts with:

```
upstream sent too big header while reading response header from upstream,
upstream: "http://127.0.0.1:4180/oauth2/callback"
```

…and surfaces 502 to the browser. v0.179.2 fixed the public callback
location with `proxy_buffer_size 16k; proxy_buffers 4 16k;`.

### Outage 2 — `/oauth2/auth` overflow (fixed in v0.179.4)

Every protected location uses `auth_request /oauth2/auth;` to validate
the session before proxying upstream. oauth2-proxy's auth_request
response carries `X-Auth-Request-User`, `X-Auth-Request-Email`,
`X-Auth-Request-Groups`, and `X-Auth-Request-Access-Token` headers.
With many group claims those response headers also exceed 4 KB, so
the *internal subrequest* fails with the same overflow. nginx returns
502 from the subrequest, which it then surfaces to the browser as
500 (the "auth request unexpected status: 502" line).

Same root cause, different location, distinct user-visible symptom.
v0.179.2 only fixed half the surface area.

## Decision

Apply `proxy_buffer_size 64k; proxy_buffers 4 64k;` to **both** the
`/oauth2/auth` and `/oauth2/callback` locations in
`collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`.

Codify the values, the rationale, and the "fix everywhere oauth2-proxy
returns headers" rule in this ADR so a future template touch does not
silently reintroduce 4 KB.

### Why 64 KB and not 16 KB or 32 KB

- Keycloak realm-roles + client-roles + group-membership claims grow
  unbounded as the operator adds organizational structure. Today's
  cookies are 8–12 KB; an org with 50 client-roles and nested groups
  pushes that past 32 KB before anyone notices.
- 64 KB covers two-token rotations (current + refresh + ID token) with
  comfortable headroom and matches what other oauth2-proxy deployment
  guides recommend (see `oauth2-proxy/docs/configuration/overview.md`
  reverse-proxy section).
- Memory cost is per-request transient: `proxy_buffers 4 64k` allocates
  4 × 64 KB only when nginx is actively reading an upstream response.
  At the edge VM's typical concurrent connection count (≤200), peak
  reservation is ~50 MB — negligible against the 4 GB VM allocation.
- Setting 64 KB once-and-for-all eliminates the "increase incrementally
  as Keycloak claims grow" maintenance treadmill, which is the failure
  mode that produced two outages in twelve hours.

### Why not just remove the auth_request

Apps rely on `X-Auth-Request-Email` / `X-Auth-Request-User` /
`X-Auth-Request-Groups` for downstream identity. Removing the
auth_request would push authentication into every app individually —
the opposite of ADR 0248 (centralized session authority).

### Why not raise nginx's default `proxy_buffer_size` globally

Global bumps affect *every* upstream, including high-cardinality apps
where 4 KB is correct and 64 KB would burn memory on idle keepalive
connections. Restrict the bump to oauth2-proxy locations where we
know the response shape.

## Consequences

- nginx edge converges with `proxy_buffer_size 64k` on both oauth2-proxy
  locations. Future Keycloak claim growth (more groups, role-mapping
  attributes, custom claims) absorbs without re-hot-patching.
- Edge VM peak memory rises by O(active_oauth2_requests × 64 KB).
  Bounded; observed marginal.
- The template comment block now reads as the canonical reference for
  the buffer values; this ADR is the deeper rationale.

## Operational Notes

- After live-apply, verify both surfaces:
  - `curl -I https://ops.<domain>/` → 200 (or 302 to oauth2 if not
    logged in), not 500.
  - Login flow completes to the protected app without 502 on the
    callback.
- If Keycloak claims grow past 64 KB (extremely unlikely), the same
  symptom returns. Treat that as a Keycloak claim-pruning task — the
  fix is to slim the JWT, not to chase nginx buffer sizes further.

## References

- v0.179.2 release notes — `/oauth2/callback` 16k fix.
- v0.179.4 release notes — `/oauth2/auth` fix and bump to 64k on both.
- nginx docs: `proxy_buffer_size`, `proxy_buffers`, `auth_request`.
- oauth2-proxy reverse-proxy guidance: header sizing under Keycloak.
