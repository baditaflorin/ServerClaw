# Incident Triage Engine

## Purpose

ADR 0114 adds a repo-managed rule-based triage engine that turns an alert payload into a ranked hypothesis list, a cheapest first action, and an optional low-risk auto-check result.

The current implementation is CPU-only and repo-local:

- the core engine runs from [`scripts/incident_triage.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/incident_triage.py)
- the Windmill wrapper lives in [`config/windmill/scripts/run-triage.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/run-triage.py)
- weekly calibration lives in [`config/windmill/scripts/calibrate-triage-rules.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/calibrate-triage-rules.py)

Until ADR 0113, ADR 0115, and ADR 0117 are implemented live, the engine uses repo-local fallback sources:

- `receipts/live-applies/` for recent deployments
- the mutation-audit local sink file for recent mutation evidence
- `config/dependency-graph.json` or explicit alert payload dependencies
- explicit alert payload metrics, logs, and certificate observations

## Entrypoints

Manual ad hoc triage from a JSON payload:

```bash
python3 scripts/incident_triage.py --payload tests/fixtures/triage-alert-payload.json
```

Manual ad hoc triage from a service id plus signal overrides:

```bash
python3 scripts/incident_triage.py \
  --service netbox \
  --alert-name netbox_health_probe_failed \
  --signal recent_deployment_within_2h=true \
  --signal error_log_count_15m=27
```

Windmill-compatible run against the mounted repo checkout:

```bash
python3 config/windmill/scripts/run-triage.py
```

Weekly rule calibration:

```bash
python3 config/windmill/scripts/calibrate-triage-rules.py
```

## Alert Payload Contract

The engine accepts a JSON object. These fields are useful:

- `service_id` or `affected_service`
- `alert_name`
- `status`
- `metrics`
- `logs`
- `dependencies`
- `certificate`
- `signal_overrides`

Minimal example:

```json
{
  "service_id": "netbox",
  "alert_name": "netbox_health_probe_failed",
  "status": "firing",
  "metrics": {
    "db_connection_count_pct": 92
  },
  "dependencies": {
    "upstream": [
      {
        "service_id": "postgres",
        "healthy": true,
        "relationship": "database"
      }
    ],
    "downstream": []
  }
}
```

## Outputs

Reports are written under `.local/triage/reports/` when `--emit` is used or when the Windmill wrapper runs with `emit=true`.

Each report contains:

- `incident_id`
- `affected_service`
- `triggered_by_alert`
- `hypotheses`
- `signal_set`
- `auto_check_result`

When `--emit` is enabled the engine also:

- writes a `triage.report_created` mutation-audit event
- optionally posts the summary to Mattermost if `LV3_TRIAGE_MATTERMOST_WEBHOOK_URL` is set

## Supported Variables

- `LV3_TRIAGE_LOKI_QUERY_URL`
- `LV3_TRIAGE_MATTERMOST_WEBHOOK_URL`
- `LV3_MUTATION_AUDIT_FILE`
- `LV3_MAINTENANCE_WINDOWS_FILE`
- `LV3_TRIAGE_CALIBRATION_WEBHOOK_URL`

## Safety Rules

- only check types listed in [`config/triage-auto-check-allowlist.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/triage-auto-check-allowlist.yaml) may auto-run
- the local auto-check executor is observation-only; it does not mutate services
- if Loki, maintenance windows, or mutation-audit history are unavailable, the engine degrades to payload-only signals instead of failing

## Verification

Local unit coverage:

```bash
uv run --with pytest --with pyyaml python -m pytest tests/test_incident_triage.py tests/test_triage_windmill.py -q
```

Data-model validation:

```bash
uv run --with pyyaml python scripts/validate_repository_data_models.py --validate
```
