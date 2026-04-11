# Runbook: OpenBao Sealed

## Severity

critical

## Alert Condition

`probe_success{service="openbao",probe_kind="readiness"} == 0`

## Immediate Steps

1. Check whether OpenBao is sealed or serving errors on `https://10.10.10.20:8200/v1/sys/health`.
2. Confirm the container is running on `docker-runtime`.
3. Pause secret-dependent changes until the health state is understood.

## Diagnosis

- Review the OpenBao health response code and the audit log for recent auth or seal events.
- Confirm the `step-ca` issued client certificate path used by the probe is still valid.
- Inspect docker runtime logs for storage or startup errors.

## Resolution

1. If OpenBao is sealed after a restart, follow the managed unseal procedure rather than forcing application restarts.
2. If the container is crash-looping, fix the runtime configuration or storage issue first.
3. Re-test the mTLS endpoint directly before resolving the alert.

## Escalation

If OpenBao remains unavailable after 15 minutes, stop any workflow that rotates or injects secrets and move to recovery procedures.

## Post-Incident

Capture whether the incident was seal state, certificate failure, or container runtime failure and record the corrective action.
