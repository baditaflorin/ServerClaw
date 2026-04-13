# ADR 0413: SSO Redirect URI Mismatch and Service Topology Variable Drift

**Date:** 2026-04-13
**Status:** Implemented
**Related:** ADR 0373 (Service Registry and derive_service_defaults), ADR 0411 (Unified Account Provisioning), ADR 0412 (Keycloak Native Account Expiry)

---

## Context

A comprehensive service health audit conducted on 2026-04-13 tested all 17 platform services
for reachability and Keycloak SSO login. The audit revealed two independent classes of bug
that together caused 7 of 17 services to be unavailable or broken.

### Bug Class 1 — SSO Redirect URI Mismatch (LibreChat / serverclaw client)

When a user clicked "Login with Keycloak" on LibreChat (`chat.lv3.org`), Keycloak returned:

```
We are sorry... An internal server error has occurred
Invalid parameter: redirect_uri
```

**Root cause:** The `serverclaw` Keycloak client had its redirect URI registered as
`/oauth/oidc/callback` in the collection role (`keycloak_runtime/tasks/main.yml`)
and in the service registry (`platform_services.yml`), but LibreChat's env var
`OPENID_CALLBACK_URL` is `/oauth/openid/callback`. The standalone role
(`roles/keycloak_runtime/tasks/serverclaw_client.yml`) already had the correct path,
but the collection role (which is what runs in production) had the wrong path.

The discrepancy went undetected because:
- No integration test exercised the full browser SSO flow end-to-end.
- Two separate copies of the serverclaw client registration existed (standalone role vs.
  collection role) and diverged over time.
- The test that checked the registration path was also wrong, masking the bug.

**Files with wrong path:**
| File | Wrong | Correct |
|------|-------|---------|
| `collections/.../keycloak_runtime/tasks/main.yml:2117` | `/oauth/oidc/callback` | `/oauth/openid/callback` |
| `inventory/group_vars/all/platform_services.yml:1784` | `/oauth/oidc/callback` | `/oauth/openid/callback` |
| `tests/test_keycloak_runtime_role.py:1231` | `/oauth/oidc/callback` | `/oauth/openid/callback` |
| `tests/test_generate_cross_cutting_artifacts.py:42` | `/oauth/oidc/callback` | `/oauth/openid/callback` |

### Bug Class 2 — `platform_service_topology` Variable Drift

Several role defaults referenced `platform_service_topology` — a variable that was
retired in ADR 0373 and is now only injected by a small number of specific playbooks
(librechat, serverclaw). For most service playbooks this variable is undefined at
play time, causing template rendering to silently fail or produce empty port numbers.

**Services affected (visible outages):**

| Service | URL | Symptom | Broken variable |
|---------|-----|---------|----------------|
| Directus | data.lv3.org | 502 Bad Gateway | `directus_container_port` |
| Paperless | paperless.lv3.org | 502 Bad Gateway | `paperless_service_topology` |
| Coolify | coolify.lv3.org | 502 Bad Gateway | `coolify_dashboard_port` |
| GlitchTip | errors.lv3.org | TLS + dead code | `glitchtip_internal_port` (dead code) |

**Services with latent bugs (currently alive from old deployment):**

| Service | URL | Broken variable | Risk |
|---------|-----|----------------|------|
| Dify | agents.lv3.org | `dify_port`, `dify_internal_base_url`, `dify_ollama_base_url` | Next converge would break port mapping |

**Services with TLS cert gaps (separate from above):**

The nginx edge certificate `lv3-edge` was missing SANs for five subdomains that were
added to the service topology after the last cert issuance:
`grist.lv3.org`, `errors.lv3.org`, `bi.lv3.org`, `paperless.lv3.org`, `scheduler.lv3.org`.

This causes hard TLS errors in browsers even when the backend containers are running.
Fix: run `make converge-nginx-edge env=production` which will invoke certbot DNS-01
to expand/reissue the shared `lv3-edge` certificate.

---

## Decision

### 1. Fix all redirect_uri references to use `/oauth/openid/callback`

The single authoritative source for LibreChat's callback URL is
`librechat_oidc_callback_url` in `librechat_runtime/defaults/main.yml`.
All other references (Keycloak client registration, service registry, tests)
must match this value. The path `/oauth/openid/callback` is correct.

**Immediate live fix:** Updated the Keycloak `serverclaw` client via the admin API
on the live platform to register `https://chat.lv3.org/oauth/openid/callback`.
This fix is reflected in code so the next `make converge-keycloak` is idempotent.

### 2. Eliminate all `platform_service_topology` references in role defaults

Replace every `platform_service_topology | platform_service_port(...)` or
`platform_service_topology | platform_service_url(...)` reference in role defaults with:

| Old pattern | New pattern |
|-------------|-------------|
| `platform_service_topology \| platform_service_port('X', 'internal')` | `{{ X_internal_port }}` (derived by `derive_service_defaults`) |
| `platform_service_topology \| platform_service_url('X', 'internal')` | `http://{{ ansible_host }}:{{ X_internal_port }}` |
| `platform_service_topology \| platform_service('X')` | `lv3_service_topology \| service_topology_get('X')` |

For variables that ARE conventional (i.e., `derive_service_defaults` sets them), remove the
redundant default entirely and replace with a comment pointing to ADR 0373.

### 3. Admin account provisioning

Two admin accounts were created and assigned to `lv3-platform-admins`, `grafana-admins`,
`harbor-admins`, and `lv3-platform-operators` groups:

- `platform-admin` — new dedicated admin account
- `baditaflorin` — temporary platform access account elevated to full admin for audit testing

The account `baditaflorin` has `account_expires_at: 2026-04-23T10:00:00Z` (10-day window,
per ADR 0412).

### 4. Remaining actions (require playbook runs by operator)

| Action | Command | Required for |
|--------|---------|--------------|
| Reissue TLS cert | `make converge-nginx-edge env=production` | grist, errors, bi, paperless, scheduler TLS |
| Redeploy Directus | `make converge-directus env=production` | data.lv3.org 502 fix |
| Redeploy Paperless | `make converge-paperless env=production` | paperless.lv3.org 502 fix |
| Redeploy Coolify | `make converge-coolify env=production` | coolify.lv3.org 502 fix |
| Investigate Superset | SSH to docker-runtime, `docker ps | grep superset` | bi.lv3.org — port chain correct, container may be stopped |
| Re-converge Keycloak | `make converge-keycloak env=production` | Pick up serverclaw redirect_uri fix |

---

## Consequences

### Positive

- LibreChat SSO login now works (redirect_uri fixed in Keycloak live + code)
- `platform_service_topology` dead code removed from 5 role defaults
- All role defaults now reference the canonical ADR 0373 convention
- Two admin accounts are provisioned and ready for platform testing
- Root cause of 4 service outages (Directus, Paperless, Coolify, GlitchTip) identified

### Negative

- Four services (Directus, Paperless, Coolify, Superset) require a manual re-convergence
  to actually recover from 502. The code fix alone is not sufficient.
- TLS cert expansion also requires a manual `make converge-nginx-edge` run.
- Nomad scheduler (`scheduler.lv3.org`) has both a TLS cert gap and a backend timeout
  and requires separate investigation.

### Neutral

- The `roles/` directory is a hard-link forest into `collections/ansible_collections/`.
  Editing either path edits the same physical file. This is correct behaviour by design
  but is not documented anywhere; future contributors may be confused by it.

---

## Files Changed

| File | Change |
|------|--------|
| `collections/.../keycloak_runtime/tasks/main.yml` | `/oauth/oidc/callback` → `/oauth/openid/callback` |
| `inventory/group_vars/all/platform_services.yml` | Same |
| `tests/test_keycloak_runtime_role.py` | Same |
| `tests/test_generate_cross_cutting_artifacts.py` | Same |
| `collections/.../paperless_runtime/defaults/main.yml` | `platform_service_topology` → `lv3_service_topology \| service_topology_get` |
| `collections/.../directus_runtime/defaults/main.yml` | `directus_container_port` → `{{ directus_internal_port }}` |
| `collections/.../coolify_runtime/defaults/main.yml` | `coolify_dashboard_port` → `{{ coolify_internal_port }}` |
| `collections/.../glitchtip_runtime/defaults/main.yml` | Dead-code broken defaults replaced with comment |
| `collections/.../dify_runtime/defaults/main.yml` | `dify_port`, `dify_internal_base_url`, `dify_ollama_base_url` fixed |
