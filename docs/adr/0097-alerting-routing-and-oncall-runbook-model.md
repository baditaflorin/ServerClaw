# ADR 0097: Alerting Routing and On-Call Runbook Model

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

The platform generates alerts from multiple sources — Grafana alert rules, SLO burn rate rules (ADR 0096), drift detection (ADR 0091), health probe failures (ADR 0064), and GlitchTip exceptions (ADR 0061). Currently:

- Grafana alerts have no configured notification channels beyond the default "do nothing"
- There is no severity model defining which alerts wake someone up versus which appear in a Mattermost channel the next morning
- There is no on-call rotation or escalation model, even informally
- Alerts have no associated runbooks; an operator who receives an alert must figure out from scratch what to do
- Maintenance windows (ADR 0080) do not suppress alerts — during a planned deployment, spurious alerts fire and are silenced manually

The result is that monitoring exists but does not close the loop: alerts are not actioned, and the platform has no defined response protocol. A finished platform product must be operable by any qualified person at any time, not just the original builder who knows the system intuitively.

## Decision

We will implement a **two-tier alert routing model** with Alertmanager as the routing engine, severity-based destination mapping, mandatory runbook links on every alert, and automatic maintenance window silences.

### Alert severity tiers

Every alert rule carries a `severity` label with one of three values:

| Severity | Meaning | Response target | Example |
|---|---|---|---|
| `critical` | Service is down or SLO fast-burn in progress | Immediate action (< 15 min) | Keycloak unreachable; Postgres down |
| `warning` | Degraded reliability or slow SLO burn; service still functional | Acknowledge within 6 hours | SLO slow-burn; cert expiring in 14 days |
| `info` | Operational event requiring no immediate action | Review at next operator session | Successful backup; deployment completed |

### Alertmanager configuration

Alertmanager is deployed as an additional service on `monitoring-lv3` alongside the existing Grafana stack:

```yaml
# alertmanager/alertmanager.yml (Ansible-templated)
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: mattermost-warning

  routes:
    - match:
        severity: critical
      receiver: ntfy-critical
      continue: true  # also send to Mattermost

    - match:
        severity: critical
      receiver: mattermost-critical

    - match:
        severity: info
      receiver: mattermost-info

receivers:
  - name: ntfy-critical
    webhook_configs:
      - url: "http://localhost:2586/platform-alerts"
        http_config:
          basic_auth:
            username: "alertmanager"
            password_file: /run/secrets/ntfy_password
        send_resolved: true

  - name: mattermost-critical
    webhook_configs:
      - url: "{{ mattermost_webhook_url }}"
        send_resolved: true

  - name: mattermost-warning
    webhook_configs:
      - url: "{{ mattermost_webhook_url }}"
        send_resolved: true

  - name: mattermost-info
    webhook_configs:
      - url: "{{ mattermost_webhook_url }}"
        send_resolved: false
```

### Notification channels

**Critical alerts:**
1. **Ntfy** (self-hosted push notifications) — delivers to operator's phone via the Ntfy Android/iOS app with high-priority notification sound. Ntfy is deployed as a lightweight Compose service on `docker-runtime-lv3`.
2. **Mattermost** `#platform-alerts-critical` channel — for context and history.

**Warning alerts:**
- **Mattermost** `#platform-alerts` channel. No phone notification; reviewed at the next operator session.

**Info alerts:**
- **Mattermost** `#platform-ops` channel. Routine operational events.

### Runbook requirement

Every Grafana alert rule must include a `runbook_url` annotation pointing to the relevant runbook in the docs site (ADR 0094):

```yaml
- alert: KeycloakDown
  expr: http_probe_success{job="keycloak"} == 0
  for: 2m
  labels:
    severity: critical
    service: keycloak
  annotations:
    summary: "Keycloak SSO is unreachable"
    description: "Keycloak has been unreachable for {{ $value }} minutes."
    runbook_url: "https://docs.lv3.org/runbooks/keycloak-down/"
    dashboard_url: "https://grafana.lv3.org/d/keycloak-overview"
```

A validation check in the repository validation gate (ADR 0087) verifies that every alert rule has both a `runbook_url` and a `severity` label before the push is accepted.

### Maintenance window silence integration

The maintenance window tool (ADR 0080) is updated to create Alertmanager silences via the Alertmanager API when a maintenance window is declared:

```python
def create_silence(window: MaintenanceWindow) -> str:
    silence = {
        "matchers": [{"name": "service", "value": window.service, "isRegex": False}],
        "startsAt": window.start.isoformat(),
        "endsAt": window.end.isoformat(),
        "createdBy": window.operator,
        "comment": f"Maintenance window: {window.reason}"
    }
    response = requests.post(f"{ALERTMANAGER_URL}/api/v2/silences", json=silence)
    return response.json()["silenceID"]
```

This replaces the manual Alertmanager UI silence creation that currently has no audit trail.

### Runbook catalogue

A runbook is a structured Markdown document in `docs/runbooks/` with the following sections:

```markdown
# Runbook: <Alert Name>

## Severity: critical | warning

## Alert Condition
What the alert fires on (copy the expr).

## Immediate Steps
1. Verify the alert is real (not a probe flap): ...
2. Check service status: `lv3 health <service>`
3. Check recent deployments: `lv3 history --service <service> --last 5`

## Diagnosis
What to look at: Loki logs, Grafana panels, service-specific checks.

## Resolution
Standard resolution steps with commands.

## Escalation
If not resolved in X minutes: ...

## Post-Incident
What to record in the mutation audit log after resolution.
```

Initial runbooks are written for: Keycloak down, Postgres down, OpenBao sealed, certificate expired, SLO fast-burn, drift critical.

### Alert deduplication

Alertmanager's `group_by: ['alertname', 'service']` ensures that if Keycloak health probe fires from three different Telegraf instances simultaneously, a single notification is sent. The `repeat_interval: 4h` prevents alert storms during an extended outage.

## Consequences

**Positive**
- Every critical alert now pages the operator's phone; nothing critical is silently dropped
- Runbook links in every alert mean any operator can respond without tribal knowledge
- Maintenance window silences are automatic and auditable; no more manual silence management
- The two-tier model prevents alert fatigue: info events do not interrupt; critical events cannot be missed

**Negative / Trade-offs**
- Ntfy must be self-hosted and the operator must have the Ntfy app installed and subscribed to the `platform-alerts` topic; this is a setup step that is easy to forget
- Alertmanager is a new service on `monitoring-lv3`; it adds a startup dependency and must be included in the backup scope
- Writing runbooks for every alert is non-trivial work; the initial set covers the most important cases but will need to grow with the platform

## Alternatives Considered

- **PagerDuty / OpsGenie**: full on-call rotation features but require SaaS subscription and external internet dependency; overkill for a single-operator homelab and introduces a dependency for a critical communication path
- **Email notifications**: always-on but no push; email is checked at best once an hour; insufficient for critical alerts
- **Grafana OnCall**: Grafana's own on-call product; adds significant complexity and requires a separate Grafana OnCall instance; Alertmanager + Ntfy achieves the same result with less overhead

## Related ADRs

- ADR 0011: Monitoring VM (Alertmanager co-located here)
- ADR 0057: Mattermost (notification destination)
- ADR 0061: GlitchTip (exception alerts route through this model)
- ADR 0064: Health probe contracts (probes generate the alert-firing metrics)
- ADR 0080: Maintenance window (window declarations create Alertmanager silences)
- ADR 0091: Continuous drift detection (drift alerts route through this model)
- ADR 0094: Developer portal (runbooks are published here)
- ADR 0096: SLO definitions (burn rate alerts route through this model)
