# Runbook: Keycloak Session Invalidation (500 at /oauth2/callback)

## Severity

high

## Symptoms

- Users hit `500 Internal Server Error` at `https://ops.example.com/oauth2/callback`
- Error detail in URL: `error=server_error&error_description=...code+not+valid`
- oauth2-proxy logs show: `invalid_grant` or `Code not valid`
- Happens immediately after Keycloak restarts or is restarted by the watchdog

## Root Cause

When Keycloak restarts, all in-flight OIDC authorization codes are invalidated.
A user who clicked "Login" before the restart has a browser holding a stale auth code.
When the browser completes the redirect to `/oauth2/callback`, Keycloak rejects it with
`invalid_grant`. oauth2-proxy turns this into a 500.

This is not a bug — it is expected behaviour after any Keycloak restart.

## User-Facing Fix (30 seconds)

Tell the affected user:

1. Close the current error tab
2. Navigate back to the service root URL (for example `https://ops.example.com/`)
3. Retry the login flow once from a clean navigation

With ADR 0381 deployed, NGINX should automatically expire both oauth2-proxy
cookies and redirect through Keycloak logout on the first failing callback. The
user should not need to clear cookies manually in the normal case.

Only fall back to manual cookie clearing if the same 500 persists after a fresh
retry and you have confirmed the platform is still serving an older edge config.

## Operator Diagnosis

```bash
# Confirm Keycloak restarted recently
ssh ops@10.10.10.92
journalctl -u 'docker-*' --since '1 hour ago' | grep -i "keycloak.*start\|restart"

# Check oauth2-proxy logs for invalid_grant
ssh ops@10.10.10.10
journalctl -u lv3-ops-portal-oauth2-proxy.service --since '30 minutes ago' \
  | grep -i "invalid_grant\|code not valid\|error"

# Verify the stale-session reset block is deployed on nginx-edge
ssh ops@10.10.10.10 \
  'grep -n "_lv3_ops_portal_proxy_csrf\|@oauth2_stale_session_reset\|oauth2/sign_in&client_id" /etc/nginx/sites-available/lv3-edge.conf'
```

## Why Keycloak Keeps Restarting

Before ADR 0376, Keycloak was restarting due to:
1. JGroups TCP timeout spam from stale `jgroups_ping` DB rows — fixed with `KC_CACHE=local`
2. No liveness monitoring — restarts went undetected for minutes

After ADR 0376:
- `KC_CACHE=local` eliminates the JGroups loop
- The identity watchdog probes the OIDC discovery endpoint every 30s
- Auto-restart is limited to 6/hr — if Keycloak is crashing more than that, there is
  a deeper problem that needs investigation, not more restarts

## If Users Keep Getting 500s

Check restart frequency:
```bash
# On runtime-control
journalctl -u lv3-identity-watchdog.service --since '2 hours ago' \
  | grep "Restarting keycloak"
# If more than 6 lines in 1 hour: watchdog hit rate limit — investigate Keycloak root cause
```

Check Keycloak health directly:
```bash
curl -s http://10.10.10.92:18080/realms/lv3/.well-known/openid-configuration \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:', d['issuer'])"
```

If Keycloak is healthy but users still get 500 after a fresh retry, treat that
as stale-session recovery drift:

1. verify `@oauth2_stale_session_reset` is present on `nginx-edge`
2. verify both `_lv3_ops_portal_proxy` and `_lv3_ops_portal_proxy_csrf` are expired in that block
3. verify the redirect target is `https://ops.example.com/`, not `/oauth2/sign_in`
4. replay the repo-managed auth converge order from ADR 0381

## Preventing Restart-Triggered Invalidations

The only way to prevent this entirely is to avoid Keycloak restarts during active sessions.
The watchdog's rate limit (6/hr) and the `KC_CACHE=local` setting are the current
mitigations. Future option: Keycloak session persistence to DB (already enabled via
postgres-vm — sessions survive container restart if Keycloak drains cleanly).

ADR 0381 adds the server-side stale-session reset path so restart-triggered
invalidations recover automatically instead of defaulting to browser cookie
clearing.

## Related

- `identity-core-watchdog.md` — the watchdog that triggers restarts
- `oauth2-proxy-restart-loop.md` — if the proxy itself is in a restart loop
- `keycloak-down.md` — if Keycloak is not responding at all
- ADR 0376: `docs/adr/0376-identity-core-vm-isolation-and-watchdog.md`
