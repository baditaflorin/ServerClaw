# Runbook: Keycloak Session Invalidation (500 at /oauth2/callback)

## Severity

high

## Symptoms

- Users hit `500 Internal Server Error` at `https://ops.lv3.org/oauth2/callback`
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

1. Clear cookies for `sso.lv3.org` (or all cookies for `*.lv3.org`)
2. Navigate back to the service URL
3. Login again from scratch

In Chrome: Settings → Privacy → Cookies → See all site data → search `lv3.org` → Delete all.

## Operator Diagnosis

```bash
# Confirm Keycloak restarted recently
ssh ops@10.10.10.92
journalctl -u 'docker-*' --since '1 hour ago' | grep -i "keycloak.*start\|restart"

# Check oauth2-proxy logs for invalid_grant
ssh ops@10.10.10.10
journalctl -u lv3-ops-portal-oauth2-proxy.service --since '30 minutes ago' \
  | grep -i "invalid_grant\|code not valid\|error"
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
# On runtime-control-lv3
journalctl -u lv3-identity-watchdog.service --since '2 hours ago' \
  | grep "Restarting keycloak"
# If more than 6 lines in 1 hour: watchdog hit rate limit — investigate Keycloak root cause
```

Check Keycloak health directly:
```bash
curl -s http://10.10.10.92:18080/realms/lv3/.well-known/openid-configuration \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:', d['issuer'])"
```

If Keycloak is healthy but users still get 500: they have stale cookies — user-facing fix above.

## Preventing Restart-Triggered Invalidations

The only way to prevent this entirely is to avoid Keycloak restarts during active sessions.
The watchdog's rate limit (6/hr) and the `KC_CACHE=local` setting are the current
mitigations. Future option: Keycloak session persistence to DB (already enabled via
postgres-vm-lv3 — sessions survive container restart if Keycloak drains cleanly).

## Related

- `identity-core-watchdog.md` — the watchdog that triggers restarts
- `oauth2-proxy-restart-loop.md` — if the proxy itself is in a restart loop
- `keycloak-down.md` — if Keycloak is not responding at all
- ADR 0376: `docs/adr/0376-identity-core-vm-isolation-and-watchdog.md`
