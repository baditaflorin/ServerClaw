# Runbook: oauth2-proxy Restart Loop

## Severity

high

## Symptoms

- Users intermittently hit `502 Bad Gateway` or `503` on any `*.example.com` subdomain
- Login redirects to `sso.example.com` briefly fail then succeed on retry
- `journalctl -u lv3-ops-portal-oauth2-proxy-watchdog.service` shows repeated:
  ```
  WARN  oauth2-proxy probe failed (status=000, failures=1/2)
  ERROR Restarting lv3-ops-portal-oauth2-proxy.service
  ```
  every ~60s on nginx-edge

## Root Cause History

**2026-04-06**: The watchdog script used `curl -sf`. The `-f` flag exits non-zero on
4xx responses. Because a healthy oauth2-proxy returns `401` to unauthenticated probes,
`-f` caused the `||` fallback to overwrite `status_code` with `000`, making a healthy
proxy look failed. Fixed: remove `-f` from the probe curl command.

## Diagnosis

```bash
# On nginx-edge — check if watchdog is restarting a healthy proxy
journalctl -u lv3-ops-portal-oauth2-proxy-watchdog.service -n 20 --no-pager

# What status code is the probe actually getting?
curl -s -o /dev/null -w "%{http_code}" -m 5 \
  -H "Host: ops.example.com" -H "X-Forwarded-Proto: https" \
  http://127.0.0.1:4180/oauth2/auth
# Expected: 401 (healthy)
# If 000: proxy is not listening — real failure
# If 401 but watchdog still restarting: script bug (see below)

# Check the failure counter
cat /run/lv3-oauth2-proxy-watchdog/failures

# Confirm proxy is actually up
systemctl is-active lv3-ops-portal-oauth2-proxy.service
ss -tlnp | grep 4180
```

## Stop an Active Restart Loop

```bash
# On nginx-edge
# 1. Reset the failure counter immediately
echo 0 | sudo tee /run/lv3-oauth2-proxy-watchdog/failures

# 2. Verify the script does NOT have -f on the probe curl
grep "curl.*status_code" /usr/local/libexec/lv3-ops-portal-oauth2-proxy-watchdog.sh
# Must be: curl -s -o /dev/null   (no -f)
# If it shows -f, hotpatch it:
sudo sed -i 's/curl -sf -o \/dev\/null -w/curl -s -o \/dev\/null -w/' \
  /usr/local/libexec/lv3-ops-portal-oauth2-proxy-watchdog.sh
```

## Fix Permanently via IaC

The authoritative template is:
`collections/ansible_collections/lv3/platform/roles/public_edge_oidc_auth/templates/lv3-ops-portal-oauth2-proxy-watchdog.sh.j2`

Ensure line 33 reads `curl -s` not `curl -sf`. Then re-converge:

```bash
ansible-playbook \
  collections/ansible_collections/lv3/platform/playbooks/public-edge.yml \
  -i inventory/hosts.yml
```

## False Positive vs Real Failure

| Watchdog output | Meaning |
|-----------------|---------|
| `status=000, failures=N` but `ss -tlnp \| grep 4180` shows port open | Script bug — `-f` flag |
| `status=000` and port 4180 not listening | oauth2-proxy crashed — real failure |
| `status=502` or `status=500` | Upstream Keycloak issue, not proxy |

## Related

- `keycloak-session-invalidation.md` — 500 errors users see after a Keycloak restart
- `identity-core-watchdog.md` — the watchdog that monitors Keycloak and step-ca
- ADR 0376: `docs/adr/0376-identity-core-vm-isolation-and-watchdog.md`
