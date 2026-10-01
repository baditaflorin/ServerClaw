# WS-0516: Restore OpenBao monitoring and complete service evidence

## Status

`in_progress`. Live inspection found Prometheus probing its own loopback address
for OpenBao. The readiness metric was therefore permanently zero and the
`OpenBaoSealed` critical alert was firing even though OpenBao's local health
endpoint returned HTTP 200. The monitoring guest is explicitly denied access to
OpenBao's private HTTP health port by the current guest firewall policy.

## Scope

Point the liveness/readiness probes at the private OpenBao guest address and
allow only the monitoring guest to reach the health API port. Add a 30-day
availability SLO and its panels to the already-provisioned SLO Overview
dashboard. Keep the existing `OpenBaoSealed` rule in the shared platform rules
file, and reference that file in OpenBao's completeness profile rather than
editing a rules file owned by another active workstream. Make the completeness
profile reflect the runtime's file-mounted configuration (not Compose
environment-secret injection). Preserve the private mTLS listener and keep this
work generic in operator-facing documentation.

The original breakglass runbook update is included from the unpublished
OpenBao documentation branch. Its stale generated-registry edits are not copied;
the active workstream source and generated registry in this branch are canonical.

## Verification and apply sequence

- Run the OpenBao changed-service completeness gate and the focused schema,
  firewall-render, Prometheus/SLO-generation, and dashboard checks.
- Verify the monitoring VM can reach `/v1/sys/health` only after the allow rule
  is applied, and that Prometheus reports readiness `1` and clears the stale
  `OpenBaoSealed` alert.
- Merge through the private repository PR workflow, then apply the network
  policy from the merged checkout and capture a live-apply receipt. No OpenBao
  container or secret state is changed by this workstream.
