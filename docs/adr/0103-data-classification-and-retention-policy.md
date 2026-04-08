# ADR 0103: Data Classification and Retention Policy

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.102.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

The platform generates and stores data across many services with no unified policy governing how long data is kept, who can access it, or what happens when it is no longer needed. The consequences are:

- **Unbounded storage growth**: Loki logs, Tempo traces, and the mutation audit log accumulate indefinitely. The monitoring VM's disk will eventually fill. Currently, the only protection is Loki's default 168-hour (7-day) retention — set as an installation default, not a deliberate policy choice.
- **Unclear access boundaries**: OpenBao secrets are accessible to service accounts with wide roles; there is no documented policy on which service may read which secret class. The access model exists in OpenBao ACL policies but is not documented at the platform level.
- **No data deletion capability**: when a service is decommissioned, there is no procedure for deleting its data from Postgres, Loki, and the audit log. Data accumulates from removed services.
- **No sensitivity classification**: the mutation audit log, Loki logs, Mattermost messages, and Grafana dashboards all potentially contain sensitive operational information (service account names, internal IPs, error messages). There is no classification guiding how they are handled.

## Decision

We will define a **platform data classification model** with four classes, assign every data store in the platform to a class, and enforce class-specific retention and access policies through a combination of Ansible configuration, Loki retention rules, and PBS backup scope.

### Data classification model

| Class | Definition | Examples |
|---|---|---|
| **Secret** | Authentication material; must never be logged or transmitted in plaintext | OpenBao secret values, TLS private keys, Keycloak client secrets, Postgres passwords |
| **Confidential** | Operational data with restricted access; requires authentication to view | Mutation audit log, Mattermost messages, Grafana dashboards, Windmill workflow outputs |
| **Internal** | Platform operational data; accessible to all authenticated operators | Service logs (Loki), traces (Tempo), health probe history, deployment receipts |
| **Public** | Intentionally published; no authentication required | Docs site (ADR 0094), public status page (ADR 0109), changelog |

### Retention policy by class and store

| Data Store | Class | Retention | Enforcement |
|---|---|---|---|
| OpenBao secrets | Secret | Indefinite (until explicit delete) | OpenBao metadata; no auto-expiry except for dynamic secrets |
| TLS private keys | Secret | Lifetime of the certificate + 7 days | step-ca cert-renewer; key deleted after renewal |
| Loki logs | Internal | 30 days | Loki `retention_period: 720h` in `loki-config.yaml` |
| Tempo traces | Internal | 14 days | Tempo `max_trace_idle_period: 336h` |
| Mutation audit log | Confidential | 1 year | Cron job purges records older than 365 days |
| Grafana annotations | Internal | 90 days | Grafana `[annotations] max_age = 2160h` |
| Windmill run history | Internal | 60 days | Windmill job retention setting |
| PBS VM snapshots | Confidential | 7 daily, 4 weekly, 3 monthly | PBS retention policy (already configured in ADR 0020) |
| Mattermost messages | Confidential | 2 years | Mattermost `DataRetentionSettings` |
| NetBox change log | Internal | 6 months | NetBox `CHANGELOG_RETENTION = 180` plus scheduled housekeeping |
| Deployment receipts | Internal | 1 year | Cron job purges `receipts/` subdirectories older than 365 days |
| Restore verification reports | Internal | 2 years | Cron job in `receipts/restore-verifications/` |
| Security scan reports | Internal | 1 year | Cron job in `receipts/security-reports/` |

### Secret class enforcement

No Secret-class data may appear in:
- Loki logs (service configurations must use environment variable injection, not command-line flags with embedded secrets)
- The mutation audit log (the audit logger redacts values from secret rotation events; only the secret path is logged, never the value)
- Grafana dashboards (dashboard variables must not expose secret values in panel text)
- Git history (enforced by Gitleaks in the validation gate, ADR 0087)

The Ansible role `preflight` is updated to verify that Docker Compose service environment files (`*.env`) are not committed to the repository and are only injected from OpenBao at runtime (ADR 0077).

### Access policy by class

| Class | Who can access |
|---|---|
| Secret | Service accounts only (via OpenBao dynamic credentials); no human direct access except break-glass |
| Confidential | Authenticated operators (Keycloak role: `platform-operator`) |
| Internal | Authenticated users (Keycloak role: `platform-read`) |
| Public | Anyone; no authentication |

This maps to the Keycloak realm roles (ADR 0056) and the API gateway role requirements (ADR 0092).

### Data catalog

`config/data-catalog.json` is a new catalog that documents every data store:

```json
{
  "data_stores": [
    {
      "id": "loki-logs",
      "service": "loki",
      "class": "internal",
      "retention_days": 30,
      "backup_included": false,
      "access_role": "platform-read",
      "pii_risk": "low",
      "notes": "Service logs; may contain internal IP addresses and error messages"
    },
    {
      "id": "audit-log",
      "service": "mutation-audit",
      "class": "confidential",
      "retention_days": 365,
      "backup_included": true,
      "access_role": "platform-operator",
      "pii_risk": "medium",
      "notes": "Operator identities (Keycloak usernames) are recorded with every mutation"
    }
  ]
}
```

This catalog is the source for the data reference page on the docs site (ADR 0094).

### Service decommission procedure

When a service is decommissioned, the following data cleanup is required:

```bash
# Service decommission data cleanup checklist
# Run via: lv3 decommission <service> --cleanup-data

1. Drop the Postgres database (if any): DROP DATABASE <service>;
2. Delete the Loki stream: DELETE via Loki admin API /loki/api/v1/admin/delete?query={service="<service>"}
3. Revoke the OpenBao policy and role for the service
4. Delete the Keycloak client (if any)
5. Remove the service's subdomain from the subdomain catalog (ADR 0076)
6. Remove the service from the service capability catalog (ADR 0033)
7. Record the decommission in the mutation audit log
```

A `scripts/decommission_service.py` script implements steps 1–6 and requires explicit operator confirmation before executing destructive steps.

## Implementation

- The canonical store inventory now lives in `config/data-catalog.json` and is validated by both `scripts/data_catalog.py` and the existing repository data-model gate.
- Monitoring automation now sets 30-day Loki retention, 14-day Tempo retention, and 90-day Grafana annotation retention.
- Mattermost runtime configuration now sets `DataRetentionSettings` to a 2-year retention window.
- NetBox runtime configuration now sets `CHANGELOG_RETENTION = 180` and installs a scheduled housekeeping timer.
- `scripts/purge_old_receipts.py` now prunes receipt directories and JSONL mutation-audit sinks from the catalog-defined retention windows, and the new `data_retention` role installs that as a systemd timer.
- `scripts/decommission_service.py` now generates or executes the service cleanup plan across PostgreSQL, Loki, OpenBao, Keycloak, and the repo catalogs.

## Consequences

**Positive**
- Storage growth is bounded; the monitoring VM disk no longer fills unboundedly with Loki data
- Every piece of data in the platform has a known owner, retention period, and access policy — answering compliance questions without a manual audit
- Secret class enforcement prevents credential leakage through logs or dashboards
- The data catalog is a single reference for understanding what data the platform holds — essential for any future compliance assessment

**Negative / Trade-offs**
- Implementing retention purge jobs for all data stores is non-trivial work; each store has its own deletion API or configuration
- The 30-day Loki retention is shorter than operators may expect; an incident from 45 days ago will have no logs — this is a deliberate trade-off for storage bounds; Grafana annotations and the mutation audit log provide context beyond 30 days
- Mattermost data retention (2 years) requires the Mattermost data retention plugin (Enterprise feature in some versions); check the version before implementing

## Alternatives Considered

- **No retention policy; let disks fill**: the current state; fails silently and usually only discovered during an incident when disk-full causes a service crash
- **Single global retention period for all data**: simpler but loses the nuance; audit logs and security reports warrant longer retention than transient operational logs
- **Use Postgres table partitioning for time-based retention**: appropriate for large-scale data pipelines; over-engineered for this platform's data volumes

## Related ADRs

- ADR 0020: Storage and backup model (backup scope is informed by data classification)
- ADR 0043: OpenBao for secrets (Secret class data is stored here)
- ADR 0052: Grafana Loki (retention_period is configured here)
- ADR 0053: Grafana Tempo (max_trace_idle_period is configured here)
- ADR 0056: Keycloak (access roles map to data classes)
- ADR 0066: Mutation audit log (Confidential class; 1-year retention)
- ADR 0077: Compose secrets injection (enforces Secret class isolation)
- ADR 0087: Validation gate (Gitleaks enforces no-secrets-in-git)
- ADR 0092: API gateway (access roles map to data class boundaries)
