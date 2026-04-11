# Runbook: Keycloak Down

## Severity

critical

## Alert Condition

`probe_success{service="keycloak",probe_kind="readiness"} == 0`

## Immediate Steps

1. Confirm the edge path is failing from `monitoring` and not just from your workstation.
2. Check the container state on `docker-runtime`: `docker ps --filter name=keycloak`.
3. Review the recent deployment and mutation history for `keycloak`.

## Diagnosis

- Query recent Keycloak logs in Loki from the `docker-runtime` dashboard.
- Verify the OIDC discovery endpoint directly on `10.10.10.20:18080`.
- Check whether OpenBao-backed runtime secrets or the database connection changed recently.

## Resolution

1. Restart the Keycloak stack only if the failure is confirmed and there is no active maintenance window.
2. If the container will not become healthy, inspect the runtime env and database reachability before retrying.
3. If the issue is edge-only, verify NGINX publication and upstream routing rather than restarting Keycloak blindly.

## Escalation

If Keycloak is still unavailable after 15 minutes, treat the event as an authentication outage and stop unrelated control-plane changes until the broker recovers.

## Post-Incident

Record the root cause, duration, and any manual restart or secret recovery in the mutation audit log and incident notes.
