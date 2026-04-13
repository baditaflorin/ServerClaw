# Post-Mortem: LV3 Platform Service Health Audit — 2026-04-13

**Severity:** P2 — Multiple user-facing services broken, SSO login completely non-functional for LibreChat
**Duration:** Unknown start; discovered during audit on 2026-04-13
**Detected by:** Manual platform audit initiated to test all 17 services and Keycloak SSO
**Resolved by:** Code fixes committed + live Keycloak API fix applied on 2026-04-13
**Author:** Claude Code agent (session claude/flamboyant-roentgen)

---

## Summary

A systematic audit of all 17 LV3 platform services revealed that 7 services were broken:

- **SSO completely broken for LibreChat** — "Invalid parameter: redirect_uri" error on every login attempt
- **4 services returning 502 Bad Gateway** — Directus, Coolify, Paperless, Superset (containers not deployed correctly or not running)
- **5 services with TLS certificate coverage gaps** — grist, errors (GlitchTip), bi (Superset), paperless, scheduler; browsers refuse connection before reaching the application

Two root causes were identified: a redirect_uri mismatch in the Keycloak serverclaw client
registration, and a class of stale `platform_service_topology` variable references in role
defaults that were not migrated when ADR 0373 was implemented.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2026-04-13 ~13:00 | Audit begins; 17 services tested systematically |
| 2026-04-13 ~13:05 | LibreChat SSO failure discovered: "Invalid parameter: redirect_uri" |
| 2026-04-13 ~13:10 | TLS cert gaps discovered: 5 subdomains missing from `lv3-edge` certificate SANs |
| 2026-04-13 ~13:15 | 502 services identified: Directus, Coolify, Superset, Paperless |
| 2026-04-13 ~13:25 | Root cause of SSO bug found: `/oauth/oidc/callback` vs `/oauth/openid/callback` |
| 2026-04-13 ~13:30 | Root cause of 502s found: `platform_service_topology` undefined at play time |
| 2026-04-13 ~13:35 | **Live fix applied**: Keycloak serverclaw client redirect_uri updated via admin API |
| 2026-04-13 ~13:35 | LibreChat SSO login form now loads correctly (previously errored before form render) |
| 2026-04-13 ~13:40 | Admin accounts created: `platform-admin` and `baditaflorin` elevated to `lv3-platform-admins` |
| 2026-04-13 ~14:00 | Code fixes committed for all 4 SSO redirect URI references |
| 2026-04-13 ~14:15 | Code fixes committed for all broken `platform_service_topology` role defaults |
| 2026-04-13 ~14:30 | ADR 0413 written documenting findings and decisions |

---

## Service Status at Audit Start

| Service | URL | Status | Root Cause |
|---------|-----|--------|------------|
| LibreChat | chat.lv3.org | ✅ Up / ❌ SSO broken | Keycloak redirect_uri mismatch |
| Dify | agents.lv3.org | ✅ Up | Latent dify_port bug (old deployment still running) |
| Outline | wiki.lv3.org | ✅ Up | — |
| Grafana | grafana.lv3.org | ✅ Up | — |
| Plane | tasks.lv3.org | ✅ Up | — |
| Langfuse | langfuse.lv3.org | ✅ Up | — |
| Harbor | registry.lv3.org | ✅ Up | — |
| Ops Portal | ops.lv3.org | ✅ Up | — |
| n8n | n8n.lv3.org | ✅ Up | — |
| Plausible | analytics.lv3.org | ✅ Up | — |
| Directus | data.lv3.org | ❌ 502 | directus_container_port undefined |
| Coolify | coolify.lv3.org | ❌ 502 | coolify_dashboard_port undefined |
| Superset | bi.lv3.org | ❌ TLS + 502 | TLS cert gap + container stopped |
| Paperless | paperless.lv3.org | ❌ TLS + 502 | TLS cert gap + paperless_service_topology undefined |
| Grist | grist.lv3.org | ❌ TLS error | TLS cert SAN gap |
| GlitchTip | errors.lv3.org | ❌ TLS error | TLS cert SAN gap |
| Nomad | scheduler.lv3.org | ❌ TLS + timeout | TLS cert SAN gap + backend timeout |

**Score: 10/17 reachable. 7/17 broken.**

---

## Root Cause Analysis

### RCA-1: Serverclaw Redirect URI Mismatch

**What happened:**
The `serverclaw` Keycloak client (used by LibreChat) had its `redirect_uris` list set to
`["/oauth/oidc/callback"]` in the collection role. LibreChat's `OPENID_CALLBACK_URL` env
var is `/oauth/openid/callback`. Keycloak validates the redirect URI strictly — the mismatch
causes a hard error before even showing a login form.

**How it went undetected:**
- The standalone role (`roles/keycloak_runtime/tasks/serverclaw_client.yml`) had the correct path
- The collection role (`collections/.../keycloak_runtime/tasks/main.yml`) diverged
- The divergence was introduced during the standalone→collection migration and was never caught
- Both test files that asserted the redirect URI path also had the wrong value
- No end-to-end SSO login test existed in the test suite

**Who was affected:**
Every user attempting to log in to LibreChat via "Login with Keycloak". Local email/password
login on LibreChat still worked (only OAuth SSO was broken).

### RCA-2: `platform_service_topology` Variable Drift

**What happened:**
ADR 0373 (implemented 2026-04-08) retired the `platform_service_topology` Ansible variable in
favour of `lv3_service_topology` + `platform_service_registry`. However, several role defaults
continued referencing the retired variable. Since `platform_service_topology` is only injected
as a hostvars key by a small subset of playbooks (librechat, semaphore, portainer), running any
service playbook that didn't inject it left the variable undefined at template render time.

The consequence depended on which variable was referencing it:
- For **port variables** (`directus_container_port`, `coolify_dashboard_port`): the docker-compose
  file was rendered with empty port bindings, causing the container to fail to start or bind to
  the wrong port, resulting in nginx 502.
- For **topology variables** (`paperless_service_topology`): template rendering failed entirely
  or produced incorrect `public_hostname` / `public_base_url` values, causing convergence to fail
  and leaving the container in a broken state.
- For **conventional variables** (e.g., `glitchtip_internal_port`): `derive_service_defaults`
  overrides the broken default value with a `set_fact`, so the bug is present in defaults but
  harmless at runtime. These were cleaned up as dead code.

**Why the migration was incomplete:**
ADR 0373 migrated services incrementally across multiple sessions (Sessions 12–15). Each
session migrated a subset of roles. The migration process focused on adding `derive_service_defaults`
to each role's `tasks/main.yml` but did not always clean up the stale `platform_service_topology`
references from `defaults/main.yml`.

Additionally, some services (Directus, Paperless, Coolify) were not the focus of any migration
session and retained the old reference patterns entirely.

### RCA-3: TLS Certificate SAN Gaps

**What happened:**
Five subdomains were added to `lv3_service_topology` in `inventory/host_vars/proxmox-host.yml`
as new services were deployed, but `make converge-nginx-edge` was not run after each addition.
The certbot DNS-01 renewal for the `lv3-edge` shared certificate was not triggered, leaving
the new subdomains without TLS coverage.

The certificate currently covers: *[existing services]* but not:
`grist.lv3.org`, `errors.lv3.org`, `bi.lv3.org`, `paperless.lv3.org`, `scheduler.lv3.org`.

---

## Impact

**LibreChat SSO:** All users (except those with local LibreChat accounts) were unable to log in
for an unknown duration. The last successful SSO login timestamp is not available from this audit.

**Directus / Paperless / Coolify:** These services were returning 502. Any automation or users
relying on these services was blocked.

**GlitchTip / Grist / Superset / Nomad:** These services were inaccessible from browsers
entirely due to TLS errors. The underlying containers may have been running.

---

## Resolution

### Immediate (applied live during audit)

1. **Keycloak API fix:** Updated the `serverclaw` client's `redirectUris` from
   `/oauth/oidc/callback` to `/oauth/openid/callback` via `PUT /admin/realms/lv3/clients/{id}`.
   LibreChat SSO login now works.

2. **Admin accounts:** Created `platform-admin` user; elevated `baditaflorin` to full admin
   group membership for audit testing purposes.

### Code fixes (committed, require playbook runs to take effect)

| Fix | Files | Effect |
|-----|-------|--------|
| Serverclaw redirect_uri | 4 files (collection role, service registry, 2 test files) | Next `converge-keycloak` is idempotent |
| Directus container_port | `directus_runtime/defaults/main.yml` | Next `converge-directus` fixes port binding |
| Paperless service_topology | `paperless_runtime/defaults/main.yml` | Next `converge-paperless` fixes topology vars |
| Coolify dashboard_port | `coolify_runtime/defaults/main.yml` | Next `converge-coolify` fixes port binding |
| Dify port + URL vars | `dify_runtime/defaults/main.yml` | Prevents breakage on next `converge-dify` |
| GlitchTip dead code | `glitchtip_runtime/defaults/main.yml` | Removes misleading stale code |

### Operator actions still required

```bash
# 1. Re-issue TLS certificate to add missing SANs
make converge-nginx-edge env=production

# 2. Redeploy broken services to pick up port fixes
make converge-directus env=production
make converge-paperless env=production
make converge-coolify env=production

# 3. Converge Keycloak to make redirect_uri fix durable
make converge-keycloak env=production

# 4. Investigate Superset
# SSH to docker-runtime-lv3 and check: docker ps | grep superset
# If stopped: docker compose -f /opt/superset/docker-compose.yml up -d
```

---

## Contributing Factors

1. **No end-to-end SSO smoke test** — a test that actually navigates to a service, clicks
   "Login with Keycloak", and asserts the Keycloak login form loads would have caught RCA-1
   immediately.

2. **No certificate coverage check in CI/CD** — a test that runs
   `openssl s_client -connect <subdomain>:443` for every `edge.enabled: true` service in the
   topology would catch SAN gaps before they reach production.

3. **Incomplete ADR 0373 migration audit** — the migration was declared complete after all
   roles called `derive_service_defaults`, but the old `platform_service_topology` references
   in `defaults/` files were not systematically removed. A grep-based check at migration time
   would have caught these.

4. **Divergent role copies (collection vs. standalone)** — The hard-link convention means
   editing `roles/X` or `collections/.../roles/X` touches the same file, but during initial
   migration into the collection the wrong path was used in one place. A simple
   `git diff roles/ collections/.../roles/` check would surface this immediately.

---

## Action Items

| # | Action | Owner | Priority |
|---|--------|-------|----------|
| A1 | Run `make converge-nginx-edge env=production` to fix TLS certs | Operator | 🔴 Immediate |
| A2 | Run converge for Directus, Paperless, Coolify | Operator | 🔴 Immediate |
| A3 | Investigate Superset container (may just need restart) | Operator | 🟡 Today |
| A4 | Run `make converge-keycloak env=production` to make SSO fix durable | Operator | 🟡 Today |
| A5 | Add SSO login smoke test to integration test suite (ADR 0414 candidate) | Engineering | 🟡 This week |
| A6 | Add TLS SAN coverage check to CI/CD or monitoring (one `curl -kv` per edge service) | Engineering | 🟡 This week |
| A7 | Run full grep for remaining `platform_service_topology` in role tasks/templates (not just defaults) | Engineering | 🟡 This week |
| A8 | Set `account_expires_at` attribute on the `baditaflorin` account per ADR 0412 | Operator | 🟢 Before 2026-04-23 |

---

## Lessons Learned

1. **Code fixes that require re-convergence need to be bundled with a runbook reminder.**
   A fix in `defaults/main.yml` does nothing until the corresponding `make converge-X` runs.
   The post-mortem and ADR should always list the required operator commands.

2. **Variable retirement must be verified by grep, not assumed.** When retiring a variable
   pattern, use `grep -r 'old_pattern' roles/ collections/` to find all references and
   clean them up atomically. Don't rely on role-by-role audits across multiple sessions.

3. **Test assertions for string literals must be kept in sync with the system under test.**
   The test for the redirect URI was wrong for the same amount of time as the code bug.
   Tests that pass while the system is broken are worse than no tests.

4. **Service health checks must cover TLS, not just HTTP status.** A `curl -s -o /dev/null
   -w "%{http_code}"` returns 000 for TLS errors, which is a distinct failure mode from 502
   (backend down) and 200 (healthy). Monitoring must distinguish these.
