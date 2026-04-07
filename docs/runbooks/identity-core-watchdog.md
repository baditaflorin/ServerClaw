# Runbook: Identity Core Watchdog

## What It Is

`lv3-identity-watchdog.timer` runs on **runtime-control-lv3** every 30 seconds.
It probes four identity-core services and auto-restarts any that fail twice in a row.

`lv3-ops-portal-oauth2-proxy-watchdog.timer` runs on **nginx-lv3** every 30 seconds.
It probes oauth2-proxy and auto-restarts it on 2 consecutive failures.

Both are part of ADR 0376. Both start on boot and survive reboots.

## Services Monitored

| Service | Host | Probe | Healthy response |
|---------|------|-------|-----------------|
| keycloak | runtime-control-lv3 | `GET /realms/lv3/.well-known/openid-configuration` on port 18080 | HTTP 200 + JSON |
| step-ca | runtime-control-lv3 | ACME health endpoint | HTTP 200 |
| openbao | runtime-control-lv3 | vault health endpoint | HTTP 200 |
| api-gateway | runtime-control-lv3 | health endpoint | HTTP 200 |
| oauth2-proxy | nginx-lv3 | `GET /oauth2/auth` on port 4180 | HTTP 401 |

## Check Watchdog Status

```bash
# On runtime-control-lv3
systemctl is-active lv3-identity-watchdog.timer
systemctl list-timers lv3-identity-watchdog.timer
journalctl -u lv3-identity-watchdog.service -n 30 --no-pager

# On nginx-lv3
systemctl is-active lv3-ops-portal-oauth2-proxy-watchdog.timer
journalctl -u lv3-ops-portal-oauth2-proxy-watchdog.service -n 10 --no-pager
cat /run/lv3-oauth2-proxy-watchdog/failures
```

## Healthy Log Output

On runtime-control-lv3 every 30s:
```
INFO  keycloak: healthy
INFO  step-ca: healthy
INFO  openbao: healthy
INFO  api-gateway: healthy
INFO  All identity-core services healthy
```

On nginx-lv3 — silent when healthy (only logs on failure or recovery).

## When a Restart Is Triggered

The watchdog will log:
```
WARN  keycloak probe failed (status=000, failures=1/2)
WARN  keycloak probe failed (status=000, failures=2/2)
ERROR Restarting keycloak (docker compose restart)
```

And send an ntfy alert to the `platform-identity-critical` topic.

Auto-restart is rate-limited to **6 restarts per hour** per service. If the limit is hit,
the watchdog stops restarting and only alerts. Manual intervention is required.

## Manually Trigger a Probe Run

```bash
# On runtime-control-lv3
systemctl start lv3-identity-watchdog.service
journalctl -u lv3-identity-watchdog.service -n 10 --no-pager
```

## Stop / Disable the Watchdog

Only do this during maintenance to prevent unwanted restarts:

```bash
# Temporary (survives until reboot)
systemctl stop lv3-identity-watchdog.timer

# Permanent (until re-enabled or re-converged)
systemctl disable lv3-identity-watchdog.timer
```

Re-enable after maintenance:
```bash
systemctl enable --now lv3-identity-watchdog.timer
```

## Watchdog Not Running

If the timer is inactive after a reboot:

```bash
# Check if service unit files exist
ls /etc/systemd/system/lv3-identity-watchdog.*

# If missing: re-converge the role
ansible-playbook \
  collections/ansible_collections/lv3/platform/playbooks/identity-core-watchdog.yml \
  -i inventory/hosts.yml
```

## Configuration

Defaults live in:
`collections/ansible_collections/lv3/platform/roles/identity_core_watchdog/defaults/main.yml`

Key variables:
- `identity_watchdog_probe_interval_sec: 30`
- `identity_watchdog_max_restarts_per_hour: 6`
- Services list under `identity_watchdog_services`

To change the interval or add a service, edit defaults and re-converge.

## Related

- `oauth2-proxy-restart-loop.md` — if the oauth2-proxy watchdog is causing restarts
- `keycloak-session-invalidation.md` — 500 errors after Keycloak restarts
- ADR 0376: `docs/adr/0376-identity-core-vm-isolation-and-watchdog.md`
