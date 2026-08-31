# Runbook: Authentik authorization-code retry

## Severity

high

## Symptoms

- A user receives an OAuth callback error immediately after an Authentik or
  edge maintenance event.
- oauth2-proxy logs contain `invalid_grant`, an expired authorization-code
  message, or a failed callback exchange.
- A fresh sign-in from the protected service root succeeds.

## Cause

OIDC authorization codes are short-lived and single-use. A browser that began
an authorization flow before an identity-provider, edge, or session change can
return with a code that is no longer valid. This is expected recovery behavior,
not a reason to weaken issuer, redirect-URI, or cookie validation.

## User-facing recovery

Ask the user to close the failed callback tab, return to the protected service
root, and start one clean sign-in. The edge stale-session reset path should
expire the affected oauth2-proxy cookies and redirect through the normal
Authentik login flow.

Only investigate browser cookie clearing when a fresh navigation fails and the
current edge configuration is known to be deployed.

## Operator diagnosis

```bash
# Confirm Authentik is healthy before diagnosing the relying party.
curl --fail --silent --show-error https://id.example.com/-/health/ready/ >/dev/null

# Inspect proxy callback failures without exposing session cookies.
journalctl -u lv3-ops-portal-oauth2-proxy.service --since '30 minutes ago' \
  | grep -i -E 'invalid_grant|code|callback|error'

# Verify the current stale-session reset configuration is present on nginx-edge.
sudo grep -n '_lv3_ops_portal_proxy_csrf\|@oauth2_stale_session_reset\|oauth2/sign_in' \
  /etc/nginx/sites-available/lv3-edge.conf
```

If Authentik is unhealthy, follow [Authentik Down](authentik-down.md). If the
provider is healthy but a fresh login still fails, validate the relying party's
declared redirect URI and Authentik provider configuration before restarting
any shared identity component.

## Prevention

Use governed converges and record planned identity or edge restarts. The
watchdog's rate limit avoids restart loops; it does not make an in-flight
authorization code durable. Keep the server-side stale-session reset path
enabled so stale callbacks recover with a clean sign-in instead of requiring
manual cookie deletion.

## Related

- [Identity Core Watchdog](identity-core-watchdog.md)
- [oauth2-proxy Restart Loop](oauth2-proxy-restart-loop.md)
- [Authentik Down](authentik-down.md)
