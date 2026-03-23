# ADR 0114: Rule-Based Incident Triage Engine

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.111.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-24

## Context

The platform has working alerting and on-call routing (ADR 0097), GlitchTip for failure signals (ADR 0061), and Loki for log aggregation (ADR 0052). When an alert fires, an operator is paged. The operator then manually:

1. Reads the alert, identifies the affected service.
2. Checks Grafana for recent metric anomalies.
3. Queries Loki for recent error logs.
4. Checks service health endpoints (ADR 0064).
5. Reviews recent mutations in the audit log (ADR 0066) to see if anything changed recently.
6. Forms a hypothesis and begins remediation.

This manual triage process is both slow and inconsistently applied. Different operators follow different sequences. Relevant signals are missed. The same failure patterns recur without being codified.

The case library (ADR 0118) will store past failure resolutions. But the missing layer is the live triage engine: the component that, on alert receipt, automatically correlates signals, scores hypotheses, and proposes the cheapest discriminating check — before any human or agent is asked to act.

## Decision

We will implement a **rule-based incident triage engine** as a Windmill workflow triggered on every firing alert from the alerting router (ADR 0097).

The first repository implementation in `0.111.0` lands as [`scripts/incident_triage.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/incident_triage.py) plus Windmill wrappers under [`config/windmill/scripts/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts). Until ADR 0113, ADR 0115, and ADR 0117 are implemented live, context assembly uses repo-local fallbacks: live-apply receipts, the existing mutation-audit sink, optional Loki queries, and explicit alert-payload dependency metadata. The report emission path currently writes `triage.report_created` into the mutation-audit stream; when ADR 0115 lands, that output should move to `ledger.events` without changing the triage rule contract.

### Triage pipeline

The engine runs in five stages:

1. **Context assembly**: fetch current world state (ADR 0113) for the affected service, its upstream and downstream dependencies (ADR 0117), recent mutations from the ledger (ADR 0115, last 2 hours), and raw log lines from Loki (last 15 minutes, log level ERROR and above).

2. **Signal extraction**: from the assembled context, extract a signal set — a flat list of named boolean and numeric signals. Examples:

```python
signals = {
    "service_health_probe_failing": True,
    "upstream_db_healthy": True,
    "recent_deployment_within_2h": True,
    "deployment_actor": "codex/adr-0113-workstream",
    "error_log_count_15m": 47,
    "tls_cert_expiry_days": 180,
    "downstream_services_affected_count": 3,
    "maintenance_window_active": False,
    "cpu_utilisation_pct": 12,
    "memory_utilisation_pct": 34,
    "disk_utilisation_pct": 61,
}
```

3. **Rule evaluation**: evaluate an ordered rule table against the signal set. Each rule declares:
   - the signal conditions it matches (AND/OR logic over signal names and value ranges)
   - a hypothesis label
   - a confidence score (0.0–1.0)
   - a list of discriminating checks to confirm or refute the hypothesis
   - the cheapest first action

4. **Hypothesis ranking**: rank all matched hypotheses by confidence descending. Return the top three with their discriminating checks.

5. **Output emission**: write the triage report to the mutation ledger (ADR 0115) with `event_type: triage_report`, post the summary to Mattermost `#platform-incidents` (ADR 0057), and optionally trigger the cheapest discriminating check automatically if `auto_check: true` is set on the top-ranked hypothesis.

### Rule table format

```yaml
# config/triage-rules.yaml

- id: recent-deployment-regression
  description: Service health probe failed within 2h of a deployment
  conditions:
    all:
      - signal: service_health_probe_failing
        value: true
      - signal: recent_deployment_within_2h
        value: true
  hypothesis: Deployment regression — the most recent deployment broke this service
  confidence: 0.85
  discriminating_checks:
    - type: rollback_preview
      workflow: rollback-service-deployment
      params:
        service: "{{ affected_service }}"
    - type: log_query
      query: 'service="{{ affected_service }}" level="error"'
      window: 30m
  cheapest_first_action: Review deployment receipt for {{ deployment_actor }}
  auto_check: false

- id: upstream-db-saturation
  description: Service errors correlate with high DB connection count
  conditions:
    all:
      - signal: service_health_probe_failing
        value: true
      - signal: upstream_db_healthy
        value: true
      - signal: db_connection_count_pct
        gte: 85
  hypothesis: Database connection pool saturation — service cannot acquire DB connections
  confidence: 0.75
  discriminating_checks:
    - type: metric_query
      datasource: prometheus
      query: 'pg_stat_activity_count{datname="{{ db_name }}"}'
    - type: log_query
      query: 'service="{{ affected_service }}" "connection pool"'
      window: 15m
  cheapest_first_action: Check pg_stat_activity for {{ db_name }} and compare to max_connections
  auto_check: true

- id: tls-cert-expiry
  description: HTTPS health probe failure correlates with cert near expiry
  conditions:
    all:
      - signal: service_health_probe_failing
        value: true
      - signal: tls_cert_expiry_days
        lte: 7
  hypothesis: TLS certificate expiry — certificate has expired or is within 7 days
  confidence: 0.90
  discriminating_checks:
    - type: cert_check
      target: "{{ affected_service }}"
  cheapest_first_action: Run step-ca renew for {{ affected_service }}
  auto_check: true
```

### Triage report output

```json
{
  "incident_id": "inc-2026-03-24-netbox-001",
  "affected_service": "netbox",
  "triggered_by_alert": "netbox_health_probe_failed",
  "triage_at": "2026-03-24T14:32:01Z",
  "hypotheses": [
    {
      "rank": 1,
      "id": "recent-deployment-regression",
      "hypothesis": "Deployment regression — the most recent deployment broke this service",
      "confidence": 0.85,
      "evidence": ["recent_deployment_within_2h=true", "deployment_actor=codex/adr-0113-workstream"],
      "discriminating_checks": [...],
      "cheapest_first_action": "Review deployment receipt for codex/adr-0113-workstream"
    }
  ],
  "signal_set": { ... },
  "rule_table_version": "0.4.1",
  "elapsed_ms": 230
}
```

### Feedback loop

When an incident is resolved, the operator records the actual root cause in the case library (ADR 0118). A weekly Windmill workflow compares triage hypotheses against recorded resolutions and computes per-rule precision and recall. Rules with precision below 0.5 are flagged for review; rules with precision above 0.9 are candidates for `auto_check: true` promotion.

## Consequences

**Positive**

- The first 3–5 minutes of every incident are handled automatically: by the time an operator reads the Mattermost alert, a ranked hypothesis list and a cheapest first action are already posted.
- Rule precision improves over time via the feedback loop without requiring model retraining.
- The triage report is a durable, auditable artifact in the mutation ledger; post-incident reviews have a record of what the platform diagnosed vs. what actually happened.
- Cheap discriminating checks that are `auto_check: true` can resolve well-understood incidents (certificate renewal, known restart loops) without operator involvement.

**Negative / Trade-offs**

- Rules must be written and maintained. Novel failure modes that match no rule will produce a low-confidence output that says very little. Rule coverage is an ongoing investment.
- Signal extraction quality depends on the world-state materializer (ADR 0113) and Loki log quality. Noisy or absent logs produce noisy or absent signals.
- Auto-check execution adds latency to the triage workflow. The engine must have explicit timeout budgets (ADR 0119) to avoid becoming an incident itself.

## Boundaries

- The triage engine proposes hypotheses and checks. It does not remediate autonomously unless `auto_check` is true for a specific, low-risk discriminating check.
- Remediation (running a rollback, rotating a secret) is always submitted as a compiled intent through the goal compiler (ADR 0112) and requires approval if the risk class demands it.
- The engine uses only CPU-local logic: rule evaluation, signal arithmetic, and Postgres/Loki queries. No LLM is invoked at runtime.

## Related ADRs

- ADR 0052: Loki logs (log surface for signal extraction)
- ADR 0057: Mattermost ChatOps (triage reports posted here)
- ADR 0058: NATS event bus (alert trigger delivery)
- ADR 0061: GlitchTip (incident opened here when triage fires)
- ADR 0064: Health probe contracts (primary health signal)
- ADR 0097: Alerting routing (trigger source for the triage engine)
- ADR 0113: World-state materializer (context assembly source)
- ADR 0115: Event-sourced mutation ledger (recent mutations surface; triage report output)
- ADR 0117: Service dependency graph (upstream/downstream blast-radius signals)
- ADR 0118: Replayable failure case library (feedback destination; historical pattern matching)
- ADR 0119: Budgeted workflow scheduler (execution budget enforcement for auto-checks)
