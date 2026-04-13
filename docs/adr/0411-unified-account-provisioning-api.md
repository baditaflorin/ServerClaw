# ADR 0411: Unified Account Provisioning API

**Date:** 2026-04-13
**Status:** Proposed
**Related:** ADR 0412 (Keycloak Native Account Expiry)

---

## Context

A manual account-creation exercise revealed that onboarding a new user to the
platform takes approximately 10 minutes and touches at least five separate admin
interfaces. The root cause is that there is no unified provisioning surface:

- Keycloak SSO covers 17+ services automatically (all services behind oauth2-proxy
  — n8n, Coolify, Plane, Grafana, etc. — get the user for free once the Keycloak
  account exists).
- Non-SSO services (Nextcloud, Mattermost, Gitea, Windmill, NetBox) each require
  a separate admin API call with different authentication schemes.
- Sending a welcome email requires SMTP access, which is only routable from within
  the platform network — not from an operator laptop.
- Account expiry is ad-hoc: currently handled only through session-based reminders
  (see ADR 0412 for the expiry half of this decision).

The platform API gateway at `api.example.com` already holds the
`lv3-admin-runtime` service account, which has admin-level access to Keycloak and
network-local access to all internal services. It is the right host for a
centralised provisioning endpoint.

### Known integration constraints

| Service | API type | Notes |
|---------|----------|-------|
| Keycloak | REST / admin-client | Primary; creates the SSO identity |
| Nextcloud | OCS Provisioning API | `POST /ocs/v1.php/cloud/users` |
| Mattermost | REST API v4 | `POST /api/v4/users` |
| Gitea | Swagger/admin API | Username `ops-gitea` already exists; new users get a distinct username |
| Windmill | REST API | `POST /api/w/{workspace}/users/add` |
| NetBox | REST API | Known v1-format token drift bug (Session 24); provisioning deferred until resolved |

---

## Decision

Build a `POST /v1/accounts` endpoint on the platform API gateway
(`api.example.com`) that provisions a new user across all reachable services in
a single API call.

### Request schema

```json
{
  "email": "user@example.com",
  "display_name": "Alice Example",
  "role": "viewer",
  "expiry_days": 10
}
```

`role` accepts `viewer` (default) or `operator`. `expiry_days` defaults to `10`;
pass `null` for a permanent account.

### Provisioning sequence

1. **Keycloak** — Create user in the `lv3` realm. Assign to the appropriate
   realm group (`/viewers` or `/operators`). Set custom attribute
   `account_expires_at` if `expiry_days` is non-null (see ADR 0412).
2. **Nextcloud** — Call OCS Provisioning API as admin; set display name and
   add user to the platform group.
3. **Mattermost** — Call REST API v4; set display name and team membership.
4. **Gitea** — Call admin API; create user account.
5. **Windmill** — Add user to the platform workspace with the appropriate role.
6. **NetBox** — Skipped in v1 (token format drift bug; tracked separately).
7. **Welcome email** — Send via platform SMTP relay (network-local from the
   gateway host). Template includes login URL, role, and expiry date if set.

Each step is attempted independently. A failure in one service does not abort
the remaining steps. The response body reports per-service status.

### Response schema

```json
{
  "user_id": "keycloak-uuid",
  "email": "user@example.com",
  "expires_at": "2026-04-23T00:00:00Z",
  "services": {
    "keycloak":    { "status": "ok" },
    "nextcloud":   { "status": "ok" },
    "mattermost":  { "status": "ok" },
    "gitea":       { "status": "ok" },
    "windmill":    { "status": "ok" },
    "netbox":      { "status": "skipped", "reason": "token-drift-bug" },
    "email":       { "status": "ok" }
  }
}
```

HTTP status is `201 Created` when Keycloak provisioning succeeds (the primary
identity). It is `500` only when Keycloak itself fails, since that would leave
no usable account. Partial non-SSO failures return `207 Multi-Status`.

### DELETE /v1/accounts/{user_id}

Disables the Keycloak account (oauth2-proxy blocks all SSO services
immediately), then removes or deactivates the service-level accounts in the
same order as provisioning. Returns a per-service status object in the same
shape as the create response.

### Authentication

All calls to `/v1/accounts` require a bearer token issued by the
`lv3-admin-runtime` Keycloak client. The endpoint is not exposed publicly; it
is only reachable from the platform management network or via the VPN.

---

## Implementation

The endpoint is implemented as a Windmill workflow (or a lightweight FastAPI
app deployed on the gateway host) with the following structure:

```
api-gateway/
  routes/
    accounts/
      create.py    ← orchestrates the provisioning steps
      delete.py    ← orchestrates the teardown steps
      providers/
        keycloak.py
        nextcloud.py
        mattermost.py
        gitea.py
        windmill.py
        email.py
```

Credentials for each provider are sourced from OpenBao (the platform secrets
manager) at runtime, not hardcoded.

---

## Consequences

### Positive

- New-user onboarding drops from ~10 minutes to a single API call
- Welcome emails are sent reliably from within the platform network
- Account expiry is set at creation time (ADR 0412 handles enforcement)
- Per-service status in the response makes partial failures visible and
  actionable without hiding them

### Negative

- Services added to the platform in future must register a provisioning
  provider here (small but ongoing maintenance cost)
- NetBox provisioning is deferred until the token-drift bug is resolved

### Neutral

- The Keycloak `account_expires_at` attribute is the canonical expiry source;
  the API only sets it — ADR 0412 enforces it
- Non-SSO service accounts are best-effort; the Keycloak account is authoritative

---

## Artifacts

| Artifact | Path |
|----------|------|
| This ADR | `docs/adr/0411-unified-account-provisioning-api.md` |
| Expiry enforcement ADR | `docs/adr/0412-keycloak-native-account-expiry.md` |
| Service registry | `inventory/group_vars/all/platform_services.yml` |
| API gateway role | `roles/api_gateway/` |
