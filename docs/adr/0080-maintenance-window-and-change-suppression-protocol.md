# ADR 0080: Maintenance Window And Change Suppression Protocol

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

As the platform adds more alerting surfaces — Uptime Kuma health checks, Grafana alert rules, NATS-routed findings from the observation loop (ADR 0071), GlitchTip error tracking, and Mattermost notifications — planned maintenance events generate noise. A routine live-apply that intentionally takes a service offline for 2 minutes triggers every health monitor for that service simultaneously.

Without a maintenance window protocol:
- operators silence alerts manually per-tool (inconsistent, often forgotten)
- agents running the observation loop (ADR 0071) emit findings for intentional outages, filling `#platform-findings` with expected downtime events
- there is no auditable record of "this downtime was planned"
- alerts resume the moment the window ends, requiring another manual action if the service takes slightly longer than expected to come back up

The observation loop explicitly references a maintenance-window mechanism as a prerequisite for avoiding alert fatigue (ADR 0071 Consequences). This ADR defines that mechanism.

## Decision

We will implement a maintenance window protocol based on a NATS KV flag and a governed open/close workflow.

### Maintenance window state

Maintenance windows are stored in NATS KV store (`maintenance-windows` bucket):

```
key:   maintenance/<service-id>
value: {
         "window_id": "<uuid>",
         "service_id": "<service-id>|all",
         "reason": "live-apply: upgrading grafana to 11.x",
         "opened_by": { "class": "operator|agent", "id": "..." },
         "opened_at": "<ISO-8601>",
         "expected_duration_minutes": 30,
         "auto_close_at": "<ISO-8601>",
         "correlation_id": "<promotion_id or live_apply_id>"
       }
```

A missing key means no active window. The value is the active window descriptor.

### Opening a window

**Manual:**
```bash
make open-maintenance-window \
  SERVICE=grafana \
  REASON="upgrading grafana to 11.x" \
  DURATION_MINUTES=30
```

**Automated (as part of the deploy pipeline, ADR 0073):**
The `deploy-and-promote` Windmill workflow opens a maintenance window for the affected service at the start of the `prod-apply` step and closes it after `post-verify` completes. Duration is set to 2× the historical P99 apply duration for that playbook.

**Broadcast:**
On window open, a `maintenance.opened` event is published to NATS and forwarded to Mattermost `#platform-ops`:
```
[MAINTENANCE OPEN] grafana — upgrading grafana to 11.x
  Opened by: operator/ops-linux
  Expected duration: 30 min
  Auto-closes at: 2026-03-22T15:30:00Z
```

### Suppression logic

Every component that emits alerts or findings checks the maintenance window state before routing:

- **Observation loop (ADR 0071):** at the start of finding emission, check `maintenance/<service-id>` and `maintenance/all` in NATS KV; if a key exists, downgrade the finding's severity to `suppressed` and omit Mattermost notification
- **Uptime Kuma:** Uptime Kuma's "maintenance mode" API is called by the same open/close workflow to pause the affected monitor
- **Grafana alerts:** alert rules for the service are silenced via the Grafana API for the window duration
- **GlitchTip:** inbound errors during the window are tagged `maintenance=true` and excluded from the default issue view

All suppressed findings are still written to Loki (ADR 0052) and the mutation audit log (ADR 0066) with a `suppressed: true` flag for post-incident review.

### Closing a window

**Automatic close:** the `auto_close_at` timestamp triggers a Windmill scheduled job that deletes the NATS KV key, resumes Uptime Kuma monitors, and unsuppresses Grafana alerts.

**Manual early close:**
```bash
make close-maintenance-window SERVICE=grafana
```

**Broadcast on close:**
```
[MAINTENANCE CLOSED] grafana — closed by: auto-close (schedule)
  Duration: 18 min (expected: 30 min)
  Health check result: OK
```

### Emergency override

If a window is accidentally left open (`maintenance/all` key), an operator can force-close all windows:
```bash
make close-maintenance-window SERVICE=all FORCE=true
```
This emits a `maintenance.force_closed` audit event and sends a Mattermost alert.

### Catalog

Active and historical windows are queryable via the agent tool registry (ADR 0069) as a `get-maintenance-windows` observe tool.

## Consequences

- Planned maintenance no longer generates alert noise; operators can deploy with confidence that `#platform-findings` will not be spammed.
- Every maintenance window is auditable: who opened it, why, for how long, and whether it correlated with a specific deployment.
- Automated windows via the deploy pipeline mean most deployments require no manual window management.
- A window left open accidentally suppresses real alerts for up to the configured maximum window duration (default: 2 hours); the emergency override and the NATS KV TTL (set to the window's `auto_close_at`) mitigate this.

## Boundaries

- Maintenance windows suppress routing of findings and alerts; they do not stop health probes from executing. Probes continue to run during a window so that the return-to-health signal is immediate when the window closes.
- Security alerts (from the observation loop's `check-certificate-expiry`, `check-secret-ages`) are not suppressible by maintenance windows; they route regardless of window state.
- Multi-service windows (e.g. maintenance on the entire docker-runtime-lv3 VM) are supported via a list of `service_id` values or the special value `all`.
