# ADR 0417: External Attack Surface Hardening

**Date:** 2026-04-14
**Status:** Accepted
**Related:** ADR 0373 (Service Registry and Derived Defaults), ADR 0374 (Cross-Cutting Service Manifest), ADR 0407 (Generic-by-Default with Local Overlay), ADR 0416 (Topology Consistency Enforcement)

---

## Context

A red-team pentest conducted on 2026-04-14 identified four issues that increase
the external attack surface of the LV3 platform:

| # | Finding | Severity | Surface |
|---|---------|----------|---------|
| 1 | LibreChat open registration with no CAPTCHA | High | `chat.example.com` |
| 2 | Internal network topology leaked via unauthenticated `/api/config` endpoint | Medium | `chat.example.com/api/config` |
| 3 | Keycloak admin console publicly reachable | High | `sso.example.com/admin/` |
| 4 | API gateway Swagger UI publicly accessible | Medium | `api.example.com/docs`, `api.example.com/openapi.json` |

### Issue 1 — LibreChat open registration

`ALLOW_REGISTRATION=true` and `ALLOW_SOCIAL_REGISTRATION=true` were hardcoded in
`roles/librechat_runtime/templates/runtime.env.j2`. Any internet user could
self-register an account and consume Anthropic/OpenAI API quota without
operator approval.

### Issue 2 — Topology leak via `/api/config`

LibreChat exposes `GET /api/config` without authentication. The response includes
`modelSpecs.preset.promptPrefix`, which contained the full system prompt for all
chat models. That prompt listed internal RFC 1918 host addresses:

```
- **Proxmox host** (10.10.10.1) — hypervisor
- **docker-runtime** (10.10.10.20) — main Docker runtime
- **runtime-control** (10.10.10.92) — control plane, agent tools
- **postgres-vm** (10.10.10.60) — shared PostgreSQL
```

These IPs are not needed by the chat assistant (which has no tools and cannot
make network calls). Their presence aids reconnaissance by disclosing which RFC
1918 subnets are in use and what roles individual hosts hold.

### Issue 3 — Keycloak admin console reachable from internet

`https://sso.example.com/admin/` was accessible to any IP. The admin console
is a high-value target: a compromised admin credential gives full SSO control
over the entire platform. Keycloak does not have failed-login IP blocking enabled
by default.

### Issue 4 — API gateway documentation publicly accessible

`/docs` (Swagger UI) and `/openapi.json` on `api.example.com` were publicly
accessible without authentication. This exposes the full API surface — endpoint
paths, parameter names, authentication schemes — to unauthenticated enumeration.

---

## Decision

### 1. LibreChat registration defaults to `false`

`ALLOW_REGISTRATION` and `ALLOW_SOCIAL_REGISTRATION` are variabilized in
`roles/librechat_runtime/templates/runtime.env.j2`:

```
ALLOW_REGISTRATION={{ librechat_allow_registration | lower }}
ALLOW_SOCIAL_LOGIN={{ librechat_allow_social_login | lower }}
ALLOW_SOCIAL_REGISTRATION={{ librechat_allow_social_registration | lower }}
```

Default values in `roles/librechat_runtime/defaults/main.yml`:

```yaml
librechat_allow_registration: false       # secure by default
librechat_allow_social_login: true        # SSO via Keycloak OIDC remains enabled
librechat_allow_social_registration: false  # secure by default
```

Operators who intentionally want open registration must set
`librechat_allow_registration: true` in their inventory overlay. This is an
explicit opt-in, not the default.

`ALLOW_SOCIAL_LOGIN` remains `true` because the platform uses Keycloak OIDC
as the primary authentication path. Disabling social login would break SSO.

### 2. System prompt for chat mode must not contain RFC 1918 IPs

`config/serverclaw/system-prompt-chat.md` (and any future chat-mode prompt) must
describe infrastructure roles without embedding RFC 1918 addresses. The "Platform
overview" section now reads:

```markdown
- **Hypervisor** — Proxmox host, manages all VMs
- **Docker runtime** — main Docker runtime (API gateway, AI services, this chat)
- **Runtime control** — control plane, agent tools
- **Postgres VM** — shared PostgreSQL
```

This rule is enforced by a static analysis regression test (see Decision 5).

### 3. Nginx edge blocks `/admin/` prefix on `sso.example.com`

The nginx edge configuration for the SSO virtual host restricts the `/admin/`
location to internal CIDRs:

```nginx
location /admin/ {
    allow 10.10.10.0/24;   # platform LAN
    allow 100.64.0.0/10;   # Tailscale CGNAT range
    deny  all;
}
```

Operators who need to access the Keycloak admin console from outside the LAN
must be connected to the Tailscale VPN. This is a consequence of this decision
(see Consequences section).

### 4. Nginx edge blocks `/docs` and `/openapi.json` on `api.example.com`

The nginx edge configuration for the API gateway virtual host restricts
documentation paths to internal CIDRs:

```nginx
location = /docs {
    allow 10.10.10.0/24;
    allow 100.64.0.0/10;
    deny  all;
}

location = /openapi.json {
    allow 10.10.10.0/24;
    allow 100.64.0.0/10;
    deny  all;
}
```

### 5. Security regression tests in CI

`tests/test_adr_0417_attack_surface_hardening.py` contains static analysis
assertions that run in CI on every push:

- `librechat_allow_registration` default is `False`
- `librechat_allow_social_registration` default is `False`
- `config/serverclaw/system-prompt-chat.md` contains no RFC 1918 IP patterns

These tests prevent future agents or operators from accidentally re-enabling
open registration or re-introducing internal IPs into the chat prompt.

---

## Consequences

### Positive

- Open registration is off by default; API key burn by anonymous users is
  prevented without operator action
- Internal network topology is no longer disclosed via the unauthenticated
  `/api/config` endpoint
- Keycloak admin console attack surface is reduced to Tailscale VPN holders
  and LAN-connected operators
- API documentation is no longer enumerable by unauthenticated external actors
- Regression tests catch future drift before it reaches production

### Negative

- Operators who need Keycloak admin console access from outside the office
  must use Tailscale VPN. This is the intended operational model (Tailscale
  is already required for SSH access to all platform hosts).
- New user onboarding for platforms that intentionally allow open registration
  requires an explicit inventory overlay — an extra step compared to the
  previous hardcoded-`true` default.

### Neutral

- `ALLOW_SOCIAL_LOGIN` remains `true`; Keycloak OIDC continues to be the
  primary authentication path. Only anonymous self-registration is blocked.
- The nginx allow-list CIDRs (`10.10.10.0/24`, `100.64.0.0/10`) are the same
  CIDRs used for other internal-only access controls on the platform.

---

## Files Changed

| File | Change |
|------|--------|
| `roles/librechat_runtime/templates/runtime.env.j2` | Variabilized `ALLOW_REGISTRATION`, `ALLOW_SOCIAL_LOGIN`, `ALLOW_SOCIAL_REGISTRATION` |
| `roles/librechat_runtime/defaults/main.yml` | Added `librechat_allow_registration: false`, `librechat_allow_social_login: true`, `librechat_allow_social_registration: false` |
| `config/serverclaw/system-prompt-chat.md` | Removed RFC 1918 IPs from "Platform overview" section |
| `docs/adr/0417-external-attack-surface-hardening.md` | This ADR |
| `tests/test_adr_0417_attack_surface_hardening.py` | Security regression tests |
