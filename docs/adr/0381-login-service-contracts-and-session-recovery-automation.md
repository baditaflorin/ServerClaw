# ADR 0381: Login Service Contracts and Session Recovery Automation

**Status:** Accepted

**Date:** 2026-04-07

**Supersedes / Extends:** ADR 0248 (Session And Logout Authority)

## Context

On 2026-04-07, `ops.lv3.org` became completely inaccessible to all operators. Every login attempt returned HTTP 500 at `/oauth2/callback`. Clearing cookies manually in the browser was the only workaround, but operators do not know to do this and should never have to.

The root cause was a three-layer failure cascade across Keycloak, oauth2-proxy, and NGINX that no single service could detect or recover from independently:

1. **Keycloak** restarted or rotated its signing keys, invalidating all previously-issued authorization codes.
2. **oauth2-proxy** received a valid-looking callback with a fresh `code` parameter, but when it exchanged the code at Keycloak's token endpoint, Keycloak returned `invalid_grant: Code not valid`. oauth2-proxy responded with HTTP 500.
3. **The browser** still held two cookies from the previous working session:
   - `_lv3_ops_portal_proxy` (session cookie) — caused oauth2-proxy to skip fresh OIDC initiation
   - `_lv3_ops_portal_proxy_csrf` (CSRF/PKCE cookie) — held a stale `code_verifier` from the old session

Every subsequent login attempt reused the stale `code_verifier` from the CSRF cookie. Keycloak's PKCE validation (`S256`) failed because the `code_verifier` did not match the `code_challenge` that accompanied the new authorization code. This produced `invalid_grant` on every attempt, regardless of how many times the user retried.

ADR 0248 established Keycloak as the session authority and defined logout choreography, but it did not address:

- **Automated recovery** when the login path itself is broken (not just logout)
- **Cookie naming contracts** between NGINX, oauth2-proxy, and Keycloak
- **PKCE stale state** where the CSRF cookie outlives the session that created it
- **Post-logout redirect URI registration** as a deployment-time contract
- **Cross-service failure detection** where a 500 at one layer must trigger cleanup at all layers

This ADR codifies the contracts, automations, and verification procedures that prevent this class of failure from recurring.

## Decision

### Contract 1: Cookie Naming and Ownership

The platform uses exactly two cookies per protected edge session. Both are set by oauth2-proxy and scoped to `.lv3.org`.

| Cookie | Owner | Purpose | PKCE Role |
|--------|-------|---------|-----------|
| `_lv3_ops_portal_proxy` | oauth2-proxy | Session token (encrypted access/refresh tokens) | None |
| `_lv3_ops_portal_proxy_csrf` | oauth2-proxy | CSRF protection + PKCE `code_verifier` storage | Holds the `code_verifier` that must match the `code_challenge` sent to Keycloak |

**Invariant:** Any operation that invalidates the session cookie MUST also invalidate the CSRF cookie. These two cookies form an atomic pair. Expiring one without the other creates an unrecoverable state where every login attempt fails silently.

**IaC Source of Truth:**

- Cookie name: `public_edge_oidc_auth_cookie_name` in `roles/public_edge_oidc_auth/defaults/main.yml`
- Cookie domain: `public_edge_oidc_auth_cookie_domain` in `roles/public_edge_oidc_auth/defaults/main.yml`
- CSRF cookie name: derived as `{cookie_name}_csrf` (oauth2-proxy convention, not configurable independently)
- NGINX references: `public_edge_session_authority.cookie_name` and `public_edge_session_authority.cookie_domain` in `inventory/group_vars/platform.yml`

### Contract 2: Stale Session Recovery Automaton

When oauth2-proxy returns HTTP 500 at `/oauth2/callback`, NGINX intercepts the error and triggers an automated recovery sequence. This is implemented in the `@oauth2_stale_session_reset` named location in `lv3-edge.conf.j2`.

**Recovery Sequence (4 steps, all server-side, no user action required):**

```
Step 1: NGINX intercepts 500 at /oauth2/callback
        ↓
Step 2: NGINX expires _lv3_ops_portal_proxy     (Max-Age=0)
        NGINX expires _lv3_ops_portal_proxy_csrf (Max-Age=0)
        ↓
Step 3: NGINX redirects to Keycloak logout endpoint
        (kills the Keycloak server-side session + clears sso.lv3.org cookies)
        ↓
Step 4: Keycloak redirects to post_logout_redirect_uri (ops.lv3.org/)
        oauth2-proxy sees no cookies → starts fresh OIDC/PKCE flow
        User lands on Keycloak login page with clean state
```

**Why each step is mandatory:**

| Step | What happens if skipped |
|------|------------------------|
| Expire session cookie | oauth2-proxy reuses the stale session, replays old codes → 500 loop |
| Expire CSRF cookie | oauth2-proxy reads stale `code_verifier` from CSRF cookie, sends wrong PKCE verifier → `invalid_grant` on every new code |
| Keycloak logout | Keycloak server-side session survives, auto-logs user back in with the same poisoned session → generates codes that are immediately "already used" |
| Redirect to `/` not `/oauth2/sign_in` | `/oauth2/sign_in` is not registered as a `post_logout_redirect_uri` in Keycloak → HTTP 400 "Invalid redirect uri" |

**Template Implementation:**

```nginx
location = /oauth2/callback {
    proxy_pass {{ protected_site.auth_proxy_upstream }};
    # ... standard proxy headers ...
    proxy_intercept_errors on;
    error_page 500 = @oauth2_stale_session_reset;
}

location @oauth2_stale_session_reset {
    add_header Set-Cookie "{{ cookie_name }}=; Path=/; Domain={{ cookie_domain }};
        Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:01 GMT; HttpOnly; Secure;
        SameSite=Lax" always;
    add_header Set-Cookie "{{ cookie_name }}_csrf=; Path=/; Domain={{ cookie_domain }};
        Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:01 GMT; HttpOnly; Secure;
        SameSite=Lax" always;
    add_header Cache-Control "no-store" always;
    return 302 {{ keycloak_logout_url }}?post_logout_redirect_uri={{ root_url }}&client_id={{ client_id }};
}
```

### Contract 3: Post-Logout Redirect URI Registration

Every `post_logout_redirect_uri` used in NGINX templates MUST be pre-registered in the corresponding Keycloak client's `valid_post_logout_redirect_uris` list. If not, Keycloak returns HTTP 400 "Invalid redirect uri" and the user sees an error page with no way forward.

**Registration source of truth:** `keycloak_*_post_logout_redirect_uris` lists in `roles/keycloak_runtime/defaults/main.yml`.

**Current registrations for `ops-portal-oauth`:**

```yaml
keycloak_ops_portal_post_logout_redirect_uris:
  - "{{ keycloak_ops_portal_root_url }}/"       # ops.lv3.org/
  - "{{ keycloak_ops_portal_root_url }}"        # ops.lv3.org
  - "{{ keycloak_session_authority.shared_logged_out_url }}"  # ops.lv3.org/.well-known/lv3/session/logged-out
```

**Rule:** The stale session recovery automaton (Contract 2) MUST redirect to a URI that is in this list. Currently that is `ops.lv3.org/`. If the redirect target changes, the Keycloak client registration MUST be updated first, and the Keycloak configuration reconverged before the NGINX template change goes live.

**Deployment ordering constraint:**

```
1. Add new URI to keycloak_*_post_logout_redirect_uris
2. Converge Keycloak (registers the URI in the client)
3. Update NGINX template to use the new URI
4. Converge public-edge (renders the new template)
```

Reversing steps 3-4 before 1-2 causes "Invalid redirect uri" for every protected site simultaneously.

### Contract 4: OIDC Flow Parameters

The platform uses PKCE (Proof Key for Code Exchange) with `S256` for all browser OIDC flows. This is configured in oauth2-proxy and cannot be disabled without breaking Keycloak's security policy.

| Parameter | Value | Source |
|-----------|-------|--------|
| `code_challenge_method` | `S256` | `roles/public_edge_oidc_auth/defaults/main.yml` |
| `cookie_expire` | `8h` | Same |
| `cookie_refresh` | `1h` | Same |
| `cookie_name` | `_lv3_ops_portal_proxy` | Same |
| `cookie_domain` | `.lv3.org` | Same |
| `redirect_url` | `https://ops.lv3.org/oauth2/callback` | Same |
| `oidc_issuer_url` | `https://sso.lv3.org/realms/lv3` | Same |
| Scopes | `openid profile email` | Same |
| Allowed groups | `/lv3-platform-admins` | Same |

**PKCE Lifecycle:**

1. oauth2-proxy generates a random `code_verifier`, computes `code_challenge = BASE64URL(SHA256(code_verifier))`
2. `code_verifier` is encrypted and stored in `_lv3_ops_portal_proxy_csrf` cookie
3. `code_challenge` is sent to Keycloak in the authorization request
4. Keycloak issues an authorization code bound to that `code_challenge`
5. On callback, oauth2-proxy reads `code_verifier` from the CSRF cookie and sends it to Keycloak's token endpoint
6. Keycloak verifies `SHA256(code_verifier) == code_challenge` — if not, `invalid_grant`

**Failure mode:** If the CSRF cookie holds a `code_verifier` from a different authorization request than the one that produced the current `code`, step 6 always fails. This is the exact failure that caused the 2026-04-07 outage.

### Contract 5: Login Health Verification

The platform MUST verify login health after any change to Keycloak, oauth2-proxy, or NGINX edge configuration.

**Automated verification (oauth2-proxy watchdog):**

The `lv3-ops-portal-oauth2-proxy-watchdog` systemd timer runs every 30 seconds and:

1. Performs an OIDC simulation probe against `https://ops.lv3.org`
2. Verifies the redirect chain: NGINX → oauth2-proxy → Keycloak authorize endpoint
3. On failure: restarts oauth2-proxy, sends ntfy alert to `platform-identity-critical` topic
4. Failure threshold: 2 consecutive failures before escalation

**Manual verification (post-converge):**

```bash
# Verify the redirect chain works end-to-end
curl -sI https://ops.lv3.org/ | grep -E 'HTTP|Location'
# Expected: 302 → /oauth2/sign_in?rd=...

curl -sI 'https://ops.lv3.org/oauth2/sign_in?rd=https://ops.lv3.org/' | grep Location
# Expected: 302 → https://sso.lv3.org/realms/lv3/protocol/openid-connect/auth?...

# Verify the stale session reset block exists and has both cookies
ssh nginx-lv3 'grep -c _lv3_ops_portal_proxy_csrf /etc/nginx/sites-available/lv3-edge.conf'
# Expected: 17 (one per protected server block)

# Verify no /oauth2/sign_in in stale session redirect targets
ssh nginx-lv3 'grep "oauth2/sign_in&client_id" /etc/nginx/sites-available/lv3-edge.conf | wc -l'
# Expected: 0
```

### Contract 6: Keycloak Availability Requirements

Keycloak (`sso.lv3.org`) is a single point of failure for all protected browser surfaces. When Keycloak is down:

- No new logins are possible across all protected sites
- Existing sessions continue working until their 8h cookie expires
- The stale session recovery automaton redirects to Keycloak logout which will fail, leaving users on a Keycloak error page

**Keycloak health monitoring:**

- Identity-core watchdog (ADR 0376): 15-second probes with auto-restart
- `KC_CACHE=local`: avoids distributed cache overhead for single-node deployment
- OpenBao sidecar provides database credentials and TLS materials

**When Keycloak is unresponsive, the admin console (`sso.lv3.org/admin/`) shows:**

> "Timeout when waiting for 3rd party check iframe message."

This is a Keycloak admin console JavaScript issue, not a backend failure. The admin console loads an iframe from the same Keycloak instance for session validation. If Keycloak is slow to respond (common after restart with cold caches), the iframe times out. **This is cosmetic** — retry after 30 seconds.

### Contract 7: Converge Ordering for Auth Changes

Any change touching authentication MUST follow this converge order:

```
1. Keycloak configuration (client registrations, redirect URIs, realm settings)
   → make converge-keycloak env=production

2. oauth2-proxy configuration (cookie settings, OIDC parameters)
   → make converge-oidc-auth env=production

3. NGINX edge publication (template rendering, stale session blocks)
   → make configure-edge-publication env=production

4. Verification (watchdog check, manual curl chain, browser test)
```

**Never** deploy NGINX templates that reference Keycloak redirect URIs before those URIs are registered in Keycloak. The deployment will appear to succeed (nginx -t passes, reload works) but the first user to hit the stale session path will see "Invalid redirect uri".

## Consequences

**Positive:**

- The stale session recovery automaton eliminates the need for users to manually clear cookies — the server handles it transparently
- Cookie naming contracts are explicit and machine-verifiable
- Post-logout redirect URI registration is documented as a deployment ordering constraint
- PKCE lifecycle is documented so future debugging starts from understanding, not guessing
- Converge ordering prevents the class of failures where NGINX references URIs not yet registered in Keycloak

**Negative / Trade-offs:**

- The stale session recovery redirects through Keycloak logout even when Keycloak's session may already be dead — this adds one unnecessary round-trip in that case, but is safe
- The CSRF cookie name `{cookie_name}_csrf` is an oauth2-proxy internal convention, not a configurable parameter — if oauth2-proxy changes this convention in a future version, the NGINX template breaks silently
- `proxy_intercept_errors on` at `/oauth2/callback` means NGINX swallows ALL 500s from oauth2-proxy at that endpoint, including ones that might not be stale-session related — the recovery sequence is safe for all cases but may mask other oauth2-proxy bugs in logs

## Incident Timeline (2026-04-07)

| Time (UTC) | Event |
|------------|-------|
| ~18:00 | Users report 500 at `ops.lv3.org` |
| 18:15 | Root cause identified: `invalid_grant: Code not valid` in oauth2-proxy logs |
| 18:30 | First fix deployed: expire session cookie, redirect to `/oauth2/sign_in` |
| 18:35 | New failure: Keycloak rejects `/oauth2/sign_in` as invalid redirect URI |
| 18:40 | Second fix: change redirect to `ops.lv3.org/` (registered URI) |
| 18:45 | New failure: Keycloak logout confirmation page creates redirect loop |
| 18:50 | Root cause deepened: stale CSRF cookie holds wrong PKCE `code_verifier` |
| 19:00 | Third fix: expire CSRF cookie in addition to session cookie |
| 19:05 | Hotpatch applied via `qm guest exec` + python3, nginx reloaded |
| 19:15 | Login verified working |
| 19:46 | First IaC converge (from stale local worktree — overwrote hotpatch) |
| 19:59 | Second hotpatch applied via Ansible ad-hoc |
| 20:02 | Correct IaC converge from updated worktree — fix is now permanent |

## Failure Mode Catalog

| Failure | Symptom | Root Cause | Automated Recovery |
|---------|---------|------------|-------------------|
| Keycloak restart / key rotation | 500 at `/oauth2/callback` | Authorization codes bound to old signing keys | Stale session reset automaton (Contract 2) |
| Stale session cookie | 500 loop on every login | oauth2-proxy replays old codes | Cookie expiry in `@oauth2_stale_session_reset` |
| Stale CSRF/PKCE cookie | `invalid_grant: Code not valid` on every login | Wrong `code_verifier` sent to Keycloak | CSRF cookie expiry in `@oauth2_stale_session_reset` |
| Unregistered post_logout_redirect_uri | HTTP 400 "Invalid redirect uri" from Keycloak | NGINX redirect target not in Keycloak client config | Prevention only: converge ordering (Contract 7) |
| Keycloak logout confirmation page | User sees "Do you want to log out?" with no progress | `skip_logout_confirmation` not set, or `id_token_hint` missing | Redirect to `/` triggers fresh oauth2-proxy flow which bypasses the confirmation |
| Keycloak admin console timeout | "Timeout when waiting for 3rd party check iframe message" | Cold cache after restart, iframe session check times out | Retry after 30 seconds; not a backend failure |
| oauth2-proxy process crash | 502 from NGINX on all auth endpoints | oauth2-proxy systemd service stopped | Watchdog auto-restart (30s cycle) |

## Verification Checklist (Post-Auth-Change)

- [ ] `curl -sI https://ops.lv3.org/` returns 302 to `/oauth2/sign_in`
- [ ] `curl -sI https://ops.lv3.org/oauth2/sign_in` returns 302 to `sso.lv3.org`
- [ ] `grep -c _lv3_ops_portal_proxy_csrf /etc/nginx/sites-available/lv3-edge.conf` returns 17
- [ ] `grep "oauth2/sign_in&client_id" /etc/nginx/sites-available/lv3-edge.conf` returns empty
- [ ] Browser test: open incognito window, navigate to `ops.lv3.org`, complete Keycloak login, verify dashboard loads
- [ ] Browser test: navigate to `tasks.lv3.org`, verify login works (same shared session)
- [ ] Watchdog is active: `systemctl is-active lv3-ops-portal-oauth2-proxy-watchdog.timer`

## Related ADRs

- **ADR 0056:** Keycloak for operator and agent SSO
- **ADR 0133:** Portal authentication by default
- **ADR 0248:** Session and logout authority (this ADR extends 0248 with recovery automation)
- **ADR 0376:** Identity core watchdog and credential isolation
- **ADR 0046:** Identity classes for humans, services, and agents

## References

- oauth2-proxy PKCE implementation: cookie-based `code_verifier` storage
- Keycloak OIDC logout specification: `post_logout_redirect_uri` must be pre-registered
- NGINX `proxy_intercept_errors`: captures upstream error responses for server-side handling
- RFC 7636 (PKCE): `code_verifier` / `code_challenge` binding prevents authorization code interception
