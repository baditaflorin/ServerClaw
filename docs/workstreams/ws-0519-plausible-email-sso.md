# WS-0519: Plausible email-scoped SSO

## Status

Live-applied. This work adds a dedicated Authentik OAuth client and loopback-only
oauth2-proxy instance for `analytics`, with an exact email allowlist kept in the
ignored local overlay. It leaves the shared operations proxy and other protected
hostnames on their current group policy.

## Scope

Resolve the OAuth2 Proxy 403 after Authentik successfully authenticates the
operator. The active account lacked the shared `0mcp-platform-admins` group,
which is required by the shared proxy. Two Authentik records currently use the
operator's email, so granting a broad group would also change access across
other protected sites. The scoped route accepts only the configured email at
Plausible; it does not grant group membership.

The Plausible completeness profile now points at its existing shared SLO
dashboard and alert rules, and explicitly records that this service does not
need an API-gateway registration. This replaces expired checklist suppressions
with the existing monitored surfaces.

## Preflight

- Change target: `analytics.example.org` only, 1 of 18 shared-auth vhosts (5.6%).
- A second local OAuth proxy and client are added; other 17 vhosts retain the
  existing proxy and policy.
- Plausible tracking endpoints remain public as presently configured.
- Applying requires starting one local service and reloading NGINX. No Plausible
  data, database, or container is changed.
- Rollback restores analytics' proxy upstream to port 4180 and removes the
  dedicated service/client. The shared operations proxy remains available.
- Runtime login identity remains a UI confirmation because credentials are not
  stored in this workstream.

## Verification

Applied from merged source commit `7152a8a848d7c9435453f82a24474ee051bda9eb`
(repository version context `0.179.48`). Both Woodpecker checks passed for PRs
[#270](https://github.com/baditaflorin/platform_server/pull/270),
[#271](https://github.com/baditaflorin/platform_server/pull/271), and
[#272](https://github.com/baditaflorin/platform_server/pull/272).

The production edge converge completed with 0 failures. The dedicated local
`/oauth2/auth` probe returned the expected 401 without a session. The public
`analytics.example.org` route redirected to Authentik using client `plausible-edge`
and the registered analytics callback; Plausible readiness returned HTTP 200.
The Operations Portal still used `ops-portal-oauth`.

On 2026-10-05, the authenticated callback reached Plausible but `/login` returned
HTTP 500 because its cookie store requires `SECRET_KEY_BASE` to be at least 64
bytes; the managed value was 61 bytes. The secret contract now requests 64
bytes, the canonical runtime secret was rotated, and only the Plausible app
container was recreated (1 of 4 project containers). The backend `/login` and
`/api/health` both returned HTTP 200 afterward. The operator account
`operator@example.com` exists, is verified, and its managed password matches.
Plausible Community Edition still presents its own account form after Authentik;
the user can sign in with the managed bootstrap password at the local protected
secret file.

The required pre-push gate also found stale generated guest-memory facts in
`inventory/group_vars/platform.yml`. The tracked file was regenerated from its
committed source using `scripts/generate_platform_vars.py`; this was a
repository-only correction and did not change any running VM.

The repo release manager declined a patch release because unrelated workstream
and gate blockers remain. The live-apply receipt is
`receipts/live-applies/ws-0519-plausible-email-sso-apply-receipt.yaml`.

## Next

Merge the runtime secret-minimum patch through the required private-source gate.
Complete the final browser dashboard confirmation after entering the managed
Plausible account credentials.
