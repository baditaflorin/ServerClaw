# ADR 0080: Maintenance Window And Change Suppression Protocol

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.86.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-23
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

**Automated:**
A shared Windmill wrapper is provided so future workflows can open and close maintenance windows without re-embedding the protocol.

**Broadcast:**
On window open, a `platform.maintenance.opened` event is published on the private NATS event plane:
```
[MAINTENANCE OPEN] grafana — upgrading grafana to 11.x
  Opened by: operator/ops-linux
  Expected duration: 30 min
  Auto-closes at: 2026-03-22T15:30:00Z
```

### Suppression logic

Every component that emits alerts or findings checks the maintenance window state before routing:

- **Observation loop (ADR 0071):** at the start of finding emission, check `maintenance/<service-id>` and `maintenance/all` in NATS KV; if a key exists, downgrade the finding's severity to `suppressed` and omit Mattermost notification
- **GlitchTip:** in the first iteration, controller-side GlitchTip forwarding is omitted for `suppressed` findings
- **Mattermost:** in the first iteration, controller-side Mattermost forwarding is omitted for `suppressed` findings

All suppressed findings are still written to the observation-loop JSON output and NATS finding subjects with a `suppressed` marker for post-incident review.

### Closing a window

**Automatic close:** the `auto_close_at` timestamp is enforced with NATS per-message TTL so the KV entry disappears without a separate scheduler.

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

If a window is accidentally left open, an operator can force-close all active windows:
```bash
make close-maintenance-window SERVICE=all FORCE=true
```
This emits `platform.maintenance.force_closed` on the private event plane.

### Catalog

Active windows are queryable via the agent tool registry (ADR 0069) as a `get-maintenance-windows` observe tool.

## Consequences

- Planned maintenance no longer generates alert noise; operators can deploy with confidence that `#platform-findings` will not be spammed.
- Every maintenance window is auditable: who opened it, why, for how long, and whether it correlated with a specific deployment.
- A window left open accidentally suppresses real alerts for up to the configured maximum window duration (default: 2 hours); the emergency override and the NATS KV TTL (set to the window's `auto_close_at`) mitigate this.
- The repository now contains the complete first-iteration contract, but the current live NATS principal set still needs a writer identity that can publish to `$KV.maintenance-windows.>` before routine live use is possible from the controller.

## Boundaries

- Maintenance windows suppress routing of findings and alerts; they do not stop health probes from executing. Probes continue to run during a window so that the return-to-health signal is immediate when the window closes.
- Security alerts (from the observation loop's `check-certificate-expiry`, `check-secret-ages`) are not suppressible by maintenance windows; they route regardless of window state.
- The first iteration supports one service id or the special value `all`, not arbitrary multi-service lists.
- Native Uptime Kuma, Grafana, and GlitchTip maintenance-mode API integrations remain follow-on work after the core NATS KV and observation-loop protocol.
