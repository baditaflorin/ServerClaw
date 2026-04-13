# ADR 0412: Keycloak Native Account Expiry

**Date:** 2026-04-13
**Status:** Proposed
**Related:** ADR 0411 (Unified Account Provisioning API)

---

## Context

Temporary platform accounts (guest access, contractor onboarding, short-lived
agent identities) currently have no automated expiry mechanism. When the
10-minute manual provisioning exercise concluded, the follow-up question —
"when does this account expire, and who enforces that?" — had no answer.

Keycloak does not have native first-class account expiry. The `enabled` flag
can be toggled, but there is no built-in scheduler to do this automatically on
a date. The options considered were:

| Option | Verdict |
|--------|---------|
| Keycloak session/token TTL | Controls token lifetime only; account persists |
| Keycloak account lockout | Manual, no scheduling |
| External cron on operator laptop | Fragile, not declarative, lost on laptop rebuild |
| Session-based reminder in Claude | Not reliable across sessions |
| Windmill scheduled workflow | Platform-native, observable, alertable — **chosen** |

The platform already runs Windmill as a workflow scheduler. Alertmanager is
already deployed for platform alerting. Both are the right tools for this job.

---

## Decision

### 1. Expiry attribute in Keycloak

Store the expiry timestamp as a custom user attribute on every temporary
account:

```
attribute name:  account_expires_at
attribute value: ISO-8601 UTC timestamp, e.g. "2026-04-23T00:00:00Z"
```

Permanent accounts omit the attribute (absence = no expiry).

The `account_expires_at` attribute is set by the provisioning API (ADR 0411)
at account creation time. It can be updated via `PATCH /v1/accounts/{user_id}`
(extend or clear expiry) or directly in the Keycloak admin UI.

### 2. Windmill scheduled workflow — daily expiry sweep

A Windmill workflow runs daily at **02:00 UTC** on the platform workspace. It:

1. Queries the Keycloak admin API for all users in the `lv3` realm that have
   `account_expires_at` set.
2. For each user where `account_expires_at < now()`:
   a. Sets `enabled: false` on the Keycloak user record.
   b. Calls the Keycloak sessions API to revoke all active sessions for that user.
   c. Appends the user ID, email, and timestamp to a structured audit log entry.
   d. Fires an Alertmanager webhook with severity `info` and label
      `event=account_expired`.
3. Logs a summary: `{checked: N, expired: M, errors: K}`.

The workflow uses the `lv3-admin-runtime` service account (same as ADR 0411).
Credentials are sourced from OpenBao at runtime.

### 3. Alertmanager integration

The `account_expired` alert is routed to the platform notification channel
(currently the ops email alias and the internal Mattermost ops channel). It is
informational — no paging, no escalation — but it creates an auditable record
that an account was disabled.

Alert payload shape:

```yaml
labels:
  alertname: AccountExpired
  event: account_expired
  severity: info
annotations:
  summary: "Account expired and disabled: {{ $labels.email }}"
  expires_at: "{{ $labels.expires_at }}"
  disabled_by: "expiry-sweep-workflow"
```

### 4. How ADR 0411 interacts with this ADR

- `POST /v1/accounts` with `expiry_days: N` sets `account_expires_at = now() + N days`.
- `POST /v1/accounts` with `expiry_days: null` omits the attribute (permanent).
- `DELETE /v1/accounts/{user_id}` disables the Keycloak account immediately,
  bypassing the scheduled sweep.
- `PATCH /v1/accounts/{user_id}` with `{ "expiry_days": 30 }` extends or adds
  expiry; `{ "expiry_days": null }` clears it (makes permanent).

### 5. What is not in scope

- Automatic deletion of accounts: disabled accounts are retained in Keycloak
  for 90 days to preserve audit trail. Hard deletion is a manual operation.
- Per-service account expiry: expiry is enforced only at the Keycloak layer.
  Non-SSO service accounts (Nextcloud, Mattermost, Gitea) become unreachable
  via SSO once the Keycloak account is disabled, but the service-level records
  are not separately deactivated by the sweep.
- Pre-expiry warning emails: out of scope for v1; can be added as a second
  workflow that fires 24h before expiry.

---

## Workflow implementation sketch

```python
# Windmill — expiry_sweep.py (runs daily at 02:00 UTC)
import httpx, openbao, datetime

def main():
    token = openbao.get_secret("keycloak/lv3-admin-runtime")
    users = keycloak_list_users_with_expiry(token)
    now = datetime.datetime.utcnow()
    for user in users:
        expiry = datetime.datetime.fromisoformat(user["attributes"]["account_expires_at"][0])
        if expiry < now:
            keycloak_disable_user(token, user["id"])
            keycloak_revoke_sessions(token, user["id"])
            fire_alertmanager(user["email"], expiry)
            log_audit(user["id"], user["email"], expiry)
```

---

## Consequences

### Positive

- Account expiry is declarative and platform-native; no laptop-resident cron jobs
- The daily sweep is observable: Windmill shows run history, logs, and errors
- Alertmanager provides an audit trail of every expiry event
- The same mechanism works for both human accounts and short-lived agent identities

### Negative

- The 24-hour sweep granularity means an account may live up to 23h59m past its
  nominal expiry. For stricter enforcement, the sweep interval can be reduced
  to hourly, or `DELETE /v1/accounts/{user_id}` can be called explicitly.
- Non-SSO service-level records are not automatically cleaned up (accepted risk
  for v1; revisit if audit requirements tighten).

### Neutral

- Keycloak custom attributes are not indexed; the sweep must fetch all users
  with the attribute set and filter in the workflow. At expected scale
  (<500 users) this is not a performance concern.
- The `lv3-admin-runtime` credential used by the sweep is the same credential
  used by ADR 0411, so rotation of that credential must update both.

---

## Artifacts

| Artifact | Path |
|----------|------|
| This ADR | `docs/adr/0412-keycloak-native-account-expiry.md` |
| Provisioning API ADR | `docs/adr/0411-unified-account-provisioning-api.md` |
| Windmill workflow | `windmill/workflows/expiry_sweep.py` (to be created) |
| Alertmanager rules | `roles/alertmanager_runtime/files/rules/platform.yml` |
| Service account | Keycloak realm `lv3`, client `lv3-admin-runtime` |
