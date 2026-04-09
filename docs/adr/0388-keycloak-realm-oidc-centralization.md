# ADR 0388: Centralize Keycloak Realm Name and OIDC Issuer URL

**Status:** Accepted
**Decision Date:** 2026-04-09
**Concern:** DRY, Fork Portability, SSO Configuration
**Depends on:** ADR 0385 (IoC Library Refactor), ADR 0373 (Service Registry)

---

## Context

After ADR 0385 eliminated hardcoded IPs and hostnames, the next most
duplicated operator-specific value is the Keycloak **realm name** `lv3`.

### Current state

The literal string `realms/lv3` appears in **34 locations across 17 role
defaults files**. Each OIDC-enabled service independently constructs its
issuer URL:

```yaml
# librechat_runtime/defaults/main.yml
librechat_oidc_issuer: https://sso.{{ platform_domain }}/realms/lv3

# outline_runtime/defaults/main.yml
outline_keycloak_issuer: https://sso.{{ platform_domain }}/realms/lv3
outline_keycloak_auth_uri: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/auth
outline_keycloak_token_uri: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/token
outline_keycloak_userinfo_uri: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/userinfo

# jupyterhub_runtime/defaults/main.yml
jupyterhub_keycloak_issuer: https://sso.{{ platform_domain }}/realms/lv3
jupyterhub_keycloak_authorize_url: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/auth
jupyterhub_keycloak_token_url: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/token
jupyterhub_keycloak_userdata_url: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/userinfo
```

Problems:

1. **Fork portability** — A fork with realm name `acme` must find and replace
   `realms/lv3` across 34 locations in 17 files. Easy to miss one.
2. **No single source of truth** — `keycloak_realm_name: lv3` exists only in
   `keycloak_runtime/defaults/main.yml`. Other roles don't reference it;
   they hardcode the value.
3. **OIDC endpoint URL duplication** — The pattern
   `https://sso.{{ platform_domain }}/realms/<realm>/protocol/openid-connect/<endpoint>`
   is manually constructed in every role. Any change to the SSO hostname
   or realm structure requires editing every consumer.
4. **Inconsistent SSO hostname** — Most roles use `sso.{{ platform_domain }}`
   but `semaphore_runtime` uses `auth.{{ platform_domain }}`, creating a
   latent bug if the SSO subdomain changes.

### What already works

- `keycloak_runtime` already defines `keycloak_realm_name: lv3` and uses
  it consistently in all its own tasks (60+ references).
- `dify_runtime` already references `{{ keycloak_realm_name }}` instead
  of hardcoding — proving the pattern works.
- `harbor_runtime` defines its own `harbor_keycloak_realm_name: lv3` —
  a local copy that should reference the central variable.

---

## Decision

### 1. Move `keycloak_realm_name` to `identity.yml`

Add to `inventory/group_vars/all/identity.yml`:

```yaml
keycloak_realm_name: "{{ platform_domain | split('.') | first }}"
```

This derives the realm name from the domain (`lv3.org` → `lv3`), matching
the existing convention. Fork operators who set `platform_domain: acme.io`
automatically get `keycloak_realm_name: acme`.

The existing `keycloak_runtime/defaults/main.yml` value (`lv3`) becomes a
fallback that the group_var overrides.

### 2. Define central OIDC URL variables in `identity.yml`

```yaml
keycloak_oidc_issuer_url: "https://sso.{{ platform_domain }}/realms/{{ keycloak_realm_name }}"
keycloak_oidc_auth_url: "{{ keycloak_oidc_issuer_url }}/protocol/openid-connect/auth"
keycloak_oidc_token_url: "{{ keycloak_oidc_issuer_url }}/protocol/openid-connect/token"
keycloak_oidc_userinfo_url: "{{ keycloak_oidc_issuer_url }}/protocol/openid-connect/userinfo"
keycloak_oidc_jwks_url: "{{ keycloak_oidc_issuer_url }}/protocol/openid-connect/certs"
keycloak_oidc_logout_url: "{{ keycloak_oidc_issuer_url }}/protocol/openid-connect/logout"
keycloak_oidc_discovery_url: "{{ keycloak_oidc_issuer_url }}/.well-known/openid-configuration"
```

### 3. Replace all `realms/lv3` literals in role defaults

Each role's OIDC variables change from hardcoded URLs to references:

```yaml
# Before (outline_runtime/defaults/main.yml):
outline_keycloak_issuer: https://sso.{{ platform_domain }}/realms/lv3
outline_keycloak_auth_uri: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/auth
outline_keycloak_token_uri: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/token
outline_keycloak_userinfo_uri: https://sso.{{ platform_domain }}/realms/lv3/protocol/openid-connect/userinfo

# After:
outline_keycloak_issuer: "{{ keycloak_oidc_issuer_url }}"
outline_keycloak_auth_uri: "{{ keycloak_oidc_auth_url }}"
outline_keycloak_token_uri: "{{ keycloak_oidc_token_url }}"
outline_keycloak_userinfo_uri: "{{ keycloak_oidc_userinfo_url }}"
```

### Affected roles (17 files, 34 replacements)

| Role | Variables affected |
|------|--------------------|
| librechat_runtime | issuer |
| paperless_runtime | issuer |
| glitchtip_runtime | server_url |
| langfuse_runtime | issuer |
| nomad_oidc_auth | discovery_url |
| public_edge_oidc_auth | issuer, login, redeem, profile, validate, jwks (6 vars) |
| outline_runtime | issuer, auth, token, userinfo |
| vikunja_runtime | issuer |
| superset_runtime | issuer |
| semaphore_runtime | issuer (also fix `auth.` → `sso.`) |
| grist_runtime | issuer |
| api_gateway_runtime | jwks, issuer, token |
| directus_runtime | issuer |
| identity_core_watchdog | health_url |
| open_webui_runtime | provider_url |
| gitea_runtime | discovery, internal_discovery |
| sftpgo_runtime | oidc_url |
| jupyterhub_runtime | issuer, authorize, token, userdata |

---

## What NOT to Do

1. **Don't auto-derive per-service OIDC variables in derive_service_defaults.**
   OIDC configuration varies too much across services (some need issuer only,
   some need all endpoints, some use discovery URLs). Keeping explicit variable
   assignments in role defaults with references to the central URLs is the
   right level of abstraction.

2. **Don't remove per-service OIDC variables.** Services must remain
   independently configurable for cases where a service uses a different
   identity provider.

---

## Validation

```bash
# Zero hardcoded realm names in role defaults
grep -r "realms/lv3" \
  collections/ansible_collections/lv3/platform/roles/*/defaults/main.yml \
  | wc -l
# Expected: 0

# Central variables resolve correctly
ansible -m debug -a "var=keycloak_realm_name" proxmox_florin
# Expected: lv3

ansible -m debug -a "var=keycloak_oidc_issuer_url" proxmox_florin
# Expected: https://sso.lv3.org/realms/lv3
```

---

## Consequences

**Positive:**
- Fork operators changing `platform_domain` automatically get correct realm
  name and all OIDC URLs — zero additional edits needed.
- SSO hostname change (`sso.` → `auth.`) requires editing one line in
  `identity.yml` instead of 17 files.
- Eliminates 34 instances of operator-specific hardcoding.

**Negative / Trade-offs:**
- Adds 8 variables to `identity.yml`. Acceptable given they eliminate 34
  scattered literals and are derived from existing variables.
- Roles that use internal Keycloak URLs (via `public_edge_oidc_auth`) still
  construct those from `keycloak_internal_base_url` + realm — these use the
  internal network path and correctly reference `keycloak_realm_name`.

---

## Related

- ADR 0385 — IoC Library Refactor (platform_domain, platform_topology_host)
- ADR 0387 — Platform DRY Consolidation (hardcoded IPs, hostname literals)
- ADR 0373 — Service Registry and Derived Defaults
