# Runbook: SLO Fast Burn

## Severity

critical or warning

## Alert Condition

`slo:<id>:error_rate_5m` and `slo:<id>:error_rate_1h` exceed the configured burn thresholds.

## Immediate Steps

1. Identify the affected `service` and `slo` labels from the alert.
2. Confirm whether a maintenance window exists before treating the burn as unplanned.
3. Open the linked Grafana dashboard and verify whether the underlying readiness probe failures are still active.

## Diagnosis

- Compare the short-window burn to the one-hour burn to decide whether the issue is a spike or a sustained regression.
- Review deployment history, recent drift findings, and the relevant service logs.
- Check whether the failure is internal-only or also visible at the published edge.

## Resolution

1. Stabilize the underlying service before spending time on long-tail cleanup.
2. Roll back the most recent risky change if the burn rate started immediately after it.
3. Keep the alert open until the probe success rate recovers and the burn metrics fall below threshold.

## Escalation

If a critical fast-burn alert persists longer than 15 minutes, stop unrelated platform changes and treat the service as incident-active until the budget consumption is back under control.

## Post-Incident

Document the burn trigger, the affected SLO, mitigation timeline, and any target adjustments needed after review.
