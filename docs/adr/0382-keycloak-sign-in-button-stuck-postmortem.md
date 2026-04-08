# ADR-0382: Keycloak Sign-In Button Stuck — Active Incident Postmortem

- **Status:** ACTIVE BUG — not fully resolved
- **Date:** 2026-04-08
- **Related:** ADR-0381 (login service contracts)

---

## Symptom

When a user navigates to any `*.lv3.org` service protected by oauth2-proxy
(e.g. `ops.lv3.org`, `tasks.lv3.org`), they are redirected to the Keycloak
login page at `sso.lv3.org`. **Clicking the "Sign In" button does nothing.**
The page remains stuck. Opening a new tab and navigating to the same URL
works — the user is auto-logged in via SSO.

Additionally, the Keycloak admin console at `sso.lv3.org/admin/master/console/`
intermittently shows:

> **Danger alert: Something went wrong**
> Timeout when waiting for 3rd party check iframe message.

## Impact

- **User-facing:** Every login attempt requires the workaround of opening a
  new browser tab. Users cannot sign in from the page they land on.
- **Admin console:** Keycloak admin access is unreliable.
- **Severity:** P1 — authentication UX is broken for all platform users.

## Timeline (2026-04-07)

| Time (UTC) | Event |
|------------|-------|
| ~18:00 | User reports ops.lv3.org returning 500 errors and redirect loops |
| ~18:30 | Root cause #1 found: `platform_service_topology` for keycloak pointed to wrong VM (`10.10.10.92` instead of `10.10.10.20`). oauth2-proxy `redeem_url`, `profile_url`, `validate_url`, `oidc_jwks_url` all hit wrong endpoint |
| ~19:00 | Hotfix: corrected `redeem_url` on live server. Login starts working in new tabs |
| ~19:30 | User reports Sign In button still stuck on the Keycloak login page |
| ~20:00 | Investigated `approval_prompt=force` parameter — confirmed Keycloak ignores it (non-standard, Google-specific) |
| ~20:30 | All four URLs hotfixed on live server to `10.10.10.20`. Topology fix committed to IaC |
| ~21:10 | Converge #1: deployed IaC fix for all oauth2-proxy URLs |
| ~22:00 | Root cause #2 found: NGINX sending `X-Frame-Options: DENY` and `frame-ancestors 'none'` for `sso.lv3.org`, blocking Keycloak's `authChecker.js` session-checking iframe |
| ~22:07 | Fix committed: changed sso.lv3.org overrides to `SAMEORIGIN` / `frame-ancestors 'self'` |
| ~22:10 | Converge #2: deployed iframe header fix. Verified headers correct on wire |
| ~22:15 | Admin console login page loads without iframe timeout error in automated test |
| ~22:20 | **User reports Sign In button STILL stuck** |

## Root Causes Identified and Fixed

### 1. Wrong Keycloak IP in service topology (FIXED)

`platform_service_topology.keycloak` in `inventory/group_vars/platform.yml`
had `private_ip: 10.10.10.92` and `internal: http://10.10.10.92:8091`.
Keycloak actually runs on `docker-runtime-lv3` at `10.10.10.20`.

This caused oauth2-proxy to send token exchange requests to the wrong
endpoint, producing "Code not valid" errors on every login callback.

**Fix:** Changed to `10.10.10.20`. Committed as `e864e7054`.

### 2. NGINX iframe blocking headers for sso.lv3.org (FIXED but insufficient)

NGINX edge config sent:
- `X-Frame-Options: DENY`
- `Content-Security-Policy: ... frame-ancestors 'none' ...`

Keycloak uses same-origin iframes for:
- `authChecker.js` — session polling on the login page
- Admin console — 3rd-party cookie check iframe

These iframes were blocked, causing timeouts.

**Fix:** Override sso.lv3.org headers to `SAMEORIGIN` / `frame-ancestors 'self'`.
Committed as `e154e7970`. Deployed via converge.

**Verification:** Response headers confirmed correct (`SAMEORIGIN`, `frame-ancestors 'self'`).
Admin console login page loads without iframe error in automated browser test.

**BUT:** User still reports Sign In button stuck. Fix was necessary but not sufficient.

## Remaining Hypotheses (UNRESOLVED)

### H1: Browser-cached CSP/headers from before the fix

The user's browser may have cached the old `frame-ancestors 'none'` CSP.
Until the cache expires or is manually cleared, the iframe will still be
blocked client-side.

**Test:** User clears browser cache and cookies for `*.lv3.org`, then retries.

### H2: Keycloak `authChecker.js` race condition

Keycloak's `authChecker.js` runs `startSessionPolling` and `checkAuthSession`
on page load. If the session check detects an active session (from another tab
or a previous login), it may attempt a JavaScript redirect that conflicts with
the form submission, leaving the page in a half-navigating state where clicks
are consumed but no navigation completes.

**Test:** Inspect browser console on the login page for JS errors. Check if
`authChecker.js` is calling `window.location.replace()` or similar.

### H3: Keycloak `session_code` expiry in form action URL

The login form's `action` attribute contains a `session_code` parameter that
expires after a few minutes. If the user waits on the login page (e.g. while
reading error messages or debugging), the session_code expires. Clicking
Sign In POSTs to an expired endpoint, Keycloak rejects it silently or
redirects back to the same login page, creating an apparent "stuck" state.

**Test:** Load the login page, immediately click Sign In (within 30 seconds).
Compare with clicking after waiting 5+ minutes.

### H4: `form-action 'self'` CSP blocking the POST

The CSP includes `form-action 'self'`. The form POSTs to
`https://sso.lv3.org/realms/lv3/login-actions/authenticate?...` which is
same-origin and should be allowed. However, if Keycloak redirects the POST
response to a different origin, `form-action` may block it.

**Test:** Check network tab for blocked requests after clicking Sign In.

### H5: Keycloak container health degradation

Keycloak health endpoint returned 404 during testing (expected path may differ).
The container might be under memory pressure or have a degraded thread pool,
causing slow or failed iframe responses even when headers are correct.

**Test:** `curl http://10.10.10.20:8091/health/ready` and
`curl http://10.10.10.20:8091/health/live` from docker-runtime-lv3.

### H6: `approval_prompt=force` interaction with Keycloak theme JS

oauth2-proxy always sends `approval_prompt=force` as a query parameter
(hardcoded default, cannot be suppressed). While Keycloak ignores unknown
OIDC parameters, the login page theme's JavaScript might be reading URL
parameters and behaving differently when it sees this value.

**Test:** Manually construct a login URL without `approval_prompt=force`
and test whether Sign In works.

## What Works

- **New tab navigation:** Going to `ops.lv3.org` in a new tab works. SSO
  auto-login via Keycloak session redirect is functional.
- **Token exchange:** oauth2-proxy correctly exchanges authorization codes
  for tokens (redeem_url now points to correct Keycloak instance).
- **Session cookies:** Both `_lv3_ops_portal_proxy` and
  `_lv3_ops_portal_proxy_csrf` cookies are set correctly.
- **Stale session recovery:** The `@oauth2_stale_session_reset` NGINX block
  correctly expires both cookies and redirects to Keycloak logout on 500.

## What Does Not Work

- **Sign In button on Keycloak login page:** Clicking does nothing. No
  visible error. Page stays on the login form.
- **Logout button on Keycloak logout page:** Same stuck behavior — button
  greys out but page never transitions.
- **Keycloak admin console:** Intermittent "3rd party check iframe" timeout
  (may now be fixed by header change — needs user verification).

## User Workaround

1. If stuck on the Keycloak login page, open a new browser tab
2. Navigate to the desired URL (e.g. `ops.lv3.org`)
3. SSO auto-login will work in the new tab

## Next Steps

1. **User verification:** Ask user to hard-refresh (`Cmd+Shift+R`) or clear
   browser cache/cookies for `*.lv3.org` and retry
2. **Browser console inspection:** Check for JS errors on the Keycloak login
   page when Sign In is clicked
3. **Network tab analysis:** Capture the full request/response cycle when
   Sign In is clicked to identify where it fails
4. **Keycloak container health:** Verify Keycloak health endpoints and
   container resource utilization
5. **Consider `preserve_upstream_security_headers: true`** for the keycloak
   service topology entry, to let Keycloak manage its own security headers
   instead of NGINX overriding them

## Files Changed During This Incident

| File | Change |
|------|--------|
| `inventory/group_vars/platform.yml` | Fixed keycloak service topology IP from `10.10.10.92` to `10.10.10.20` |
| `roles/public_edge_oidc_auth/templates/oauth2-proxy.cfg.j2` | Added comment about `approval_prompt=force` being harmless |
| `roles/nginx_edge_publication/defaults/main.yml` | Changed sso.lv3.org `x_frame_options` to `SAMEORIGIN`, `frame-ancestors` to `'self'` |
| `docs/adr/0381-login-service-contracts-and-session-recovery-automation.md` | Login service contracts documentation |

## Commits

- `e864e7054` — fix: Keycloak service topology pointed to wrong VM
- `dfca8218c` — docs(oauth2-proxy): note that approval_prompt=force is harmless
- `e154e7970` — fix(sso): allow same-origin iframes for Keycloak session management
