# Runbook: Keycloak Down

## Severity

critical

## Alert Condition

`probe_success{service="keycloak",probe_kind="readiness"} == 0`

## Immediate Steps

1. Confirm the edge path is failing from `monitoring` and not just from your workstation.
2. Check the Keycloak container state on `runtime-control`: `docker compose --file /opt/keycloak/docker-compose.yml ps`.
3. Review the recent deployment and mutation history for both `keycloak` and `nginx_edge_publication`.

## Diagnosis

- Query recent Keycloak logs in Loki from the `runtime-control` dashboard.
- Verify the OIDC discovery endpoint directly on the runtime-local Keycloak listener on `runtime-control`.
- Check whether the public edge is still publishing the active shared TLS lineage for `sso.example.com` and `home.example.com`.
- Check whether OpenBao-backed runtime secrets or the database connection changed recently.

## Resolution

1. Replay the governed workflow first: `make live-apply-service service=keycloak env=production ALLOW_IN_PLACE_MUTATION=true`.
2. Restart the Keycloak stack only if the failure is confirmed and there is no active maintenance window.
3. If the container will not become healthy, inspect the runtime env and database reachability before retrying.
4. If the issue is edge-only, verify NGINX publication, upstream routing, and the rendered certificate lineage rather than restarting Keycloak blindly.

## Escalation

If Keycloak is still unavailable after 15 minutes, treat the event as an authentication outage and stop unrelated control-plane changes until the broker recovers.

## Post-Incident

Record the root cause, duration, any manual restart or secret recovery, and any
shared-edge certificate-lineage findings in the mutation audit log and incident
notes.
