# ADR 0096: SLO Definitions and Error Budget Tracking

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-23

## Context

The platform has comprehensive monitoring (Grafana, Loki, Tempo) and health probes for every service (ADR 0064), but no formal definition of what "good" looks like. As a result:

- An alert fires when a service is down, but there is no target to measure against. Is one minute of Keycloak downtime per month acceptable? Per week? There is no answer.
- The environment promotion gate (ADR 0073) checks that services are healthy at a point in time before promotion, but does not ask whether they have been reliably healthy over a rolling window.
- Incident retrospectives have no baseline to measure regression against: was this month worse than last month? Nobody knows.
- Operators routinely make configuration changes without knowing whether those changes degraded reliability. There is no burn rate signal to indicate "you are consuming your error budget faster than you are earning it."

Service Level Objectives (SLOs) are the standard tool for answering these questions. An SLO defines: for a given service and indicator, what fraction of time must it meet a defined threshold? The complement — the fraction of time it may fail — is the **error budget**. The burn rate of the error budget is the primary signal for whether reliability is improving or degrading.

## Decision

We will define SLOs for all edge-published and control-plane services, implement recording rules in Prometheus/Grafana to track compliance in real time, and expose error budget status in the ops portal and the promotion gate.

### SLO definitions

SLOs are defined in `config/slo-catalog.json`:

```json
{
  "slos": [
    {
      "id": "keycloak-availability",
      "service": "keycloak",
      "indicator": "uptime",
      "objective_percent": 99.5,
      "window_days": 30,
      "probe": "http_probe_success{job='keycloak'}",
      "description": "Keycloak SSO is available (HTTP 200) 99.5% of the time over a 30-day rolling window"
    },
    {
      "id": "keycloak-latency",
      "service": "keycloak",
      "indicator": "latency",
      "objective_percent": 95.0,
      "threshold_ms": 500,
      "window_days": 30,
      "probe": "http_probe_duration_seconds{job='keycloak'} < 0.5",
      "description": "95% of Keycloak probes complete in under 500ms over a 30-day rolling window"
    },
    {
      "id": "grafana-availability",
      "service": "grafana",
      "indicator": "uptime",
      "objective_percent": 99.0,
      "window_days": 30,
      "probe": "http_probe_success{job='grafana'}"
    },
    {
      "id": "ops-portal-availability",
      "service": "ops-portal",
      "indicator": "uptime",
      "objective_percent": 99.0,
      "window_days": 30,
      "probe": "http_probe_success{job='ops-portal'}"
    },
    {
      "id": "uptime-kuma-availability",
      "service": "uptime-kuma",
      "indicator": "uptime",
      "objective_percent": 99.9,
      "window_days": 30,
      "probe": "http_probe_success{job='uptime-kuma'}"
    },
    {
      "id": "api-gateway-availability",
      "service": "api-gateway",
      "indicator": "uptime",
      "objective_percent": 99.5,
      "window_days": 30,
      "probe": "http_probe_success{job='api-gateway'}"
    }
  ]
}
```

### SLI recording rules

A `scripts/generate_slo_rules.py` script reads `config/slo-catalog.json` and generates Prometheus recording rules written to `config/grafana/provisioning/rules/slo_rules.yml`:

```yaml
groups:
  - name: slo_recording_rules
    interval: 60s
    rules:
      # Error rate over 5-minute window (short burn rate)
      - record: slo:keycloak_availability:error_rate_5m
        expr: 1 - avg_over_time(http_probe_success{job="keycloak"}[5m])

      # Error rate over 1-hour window (medium burn rate)
      - record: slo:keycloak_availability:error_rate_1h
        expr: 1 - avg_over_time(http_probe_success{job="keycloak"}[1h])

      # Error budget remaining (fraction, 0–1)
      - record: slo:keycloak_availability:budget_remaining
        expr: |
          1 - (
            sum_over_time((1 - http_probe_success{job="keycloak"})[30d:1m])
            /
            (30 * 24 * 60)
            /
            (1 - 0.995)
          )
```

### Burn rate alerts

The SLO rules drive two burn rate alerts per SLO — multi-window, multi-burn-rate (MWMB) as defined by the Google SRE Workbook:

```yaml
# Fast burn: consuming error budget 14× faster than sustainable → page in 1h
- alert: SLOFastBurn_keycloak_availability
  expr: |
    slo:keycloak_availability:error_rate_5m > (14 * (1 - 0.995))
    and
    slo:keycloak_availability:error_rate_1h > (14 * (1 - 0.995))
  for: 2m
  labels:
    severity: critical
    slo: keycloak-availability
  annotations:
    summary: "Keycloak availability SLO fast burn (14× rate)"

# Slow burn: consuming at 3× rate → ticket within 6 hours
- alert: SLOSlowBurn_keycloak_availability
  expr: |
    slo:keycloak_availability:error_rate_1h > (3 * (1 - 0.995))
  for: 60m
  labels:
    severity: warning
    slo: keycloak-availability
```

These alerts are generated for every SLO entry in the catalog by `scripts/generate_slo_rules.py`.

### Grafana SLO dashboard

A dedicated **SLO Overview** Grafana dashboard is generated from the catalog, with one row per service:

| Column | Metric |
|---|---|
| Current availability (30d) | `1 - slo:<id>:error_rate_30d` |
| Error budget remaining | `slo:<id>:budget_remaining` as percent |
| Budget burn rate (1h) | Normalised error rate vs target |
| Time to budget exhaustion | Projected days at current burn rate |
| Status | RAG colour based on budget remaining (>50% green, 10–50% yellow, <10% red) |

### Promotion gate integration

The environment promotion gate (ADR 0073) is updated to check SLO status before approving a promotion from staging to production:

```python
def check_slo_gate(env: str) -> GateResult:
    for slo in load_slo_catalog():
        budget = query_prometheus(f"slo:{slo['id']}:budget_remaining")
        if budget < 0.10:  # Less than 10% error budget remaining
            return GateResult.FAIL(f"SLO {slo['id']} has less than 10% error budget remaining")
    return GateResult.PASS
```

Promotions are blocked when any SLO has less than 10% error budget remaining, preventing a degraded platform from receiving new deployments that could make it worse.

### Ops portal integration

The ops portal (ADR 0093) displays an **SLO Status** section with the same RAG indicators. Clicking an SLO opens the Grafana SLO dashboard deep-linked to that service.

## Consequences

**Positive**
- Platform reliability has a defined, measurable baseline for the first time; incidents can be measured against it
- Burn rate alerts give early warning (6+ hours) before a complete SLO breach — reactive paging becomes proactive
- The promotion gate blocking on low error budget prevents deploying into a degraded platform
- The SLO catalog is machine-readable and drives code generation; adding a new service requires adding one JSON object

**Negative / Trade-offs**
- The initial SLO targets (99.5% for Keycloak, etc.) are estimates; they will need to be calibrated against 30 days of actual data before they are meaningful
- Multi-window burn rate alerts (MWMB) have a learning curve; operators must understand what "14× burn rate" means to act correctly on it
- The recording rules add ~20 Prometheus series per SLO; for six SLOs that is 120 additional series — well within the capacity of a single Prometheus on the monitoring VM

## Alternatives Considered

- **Uptime Kuma status percentages**: Uptime Kuma already tracks uptime percentages; but it has no burn rate concept, no error budget, no promotion gate integration, and no machine-readable SLO definition — it measures the same underlying signal but cannot answer "how fast are we burning the budget?"
- **External SLO service (Nobl9, Pyrra)**: SaaS or separate operator; over-engineered for a homelab; Pyrra (open-source) could work but adds a new service for a problem solvable with Prometheus recording rules
- **Informal SLOs as comments**: documenting targets in ADRs without enforcement; humans forget and the targets drift from what is actually measured

## Related ADRs

- ADR 0011: Monitoring VM (Prometheus recording rules run here)
- ADR 0064: Health probe contracts (probes are the SLI data source)
- ADR 0073: Environment promotion gate (blocked on low error budget)
- ADR 0091: Continuous drift detection (drift can be an SLO-impacting event)
- ADR 0092: Unified platform API gateway (API gateway has its own SLO)
- ADR 0093: Interactive ops portal (SLO status section)
- ADR 0097: Alerting routing (burn rate alerts route through this model)
