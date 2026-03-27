# Runbook: Postgres Down

## Severity

critical

## Alert Condition

`probe_success{service="postgres",probe_kind="readiness"} == 0`

## Immediate Steps

1. Confirm the TCP readiness probe is failing from `monitoring-lv3`.
2. Check PostgreSQL service state on `postgres-lv3`: `systemctl status postgresql`.
3. Verify disk pressure and recent restart history before making changes.

## Diagnosis

- Inspect PostgreSQL logs and the guest dashboard for CPU, memory, and disk saturation.
- Confirm the VM is reachable over SSH and that nftables did not block the listener.
- Validate that dependent services are not flooding the database with failed connection loops.

## Resolution

1. If PostgreSQL is stopped, restart the service and confirm port `5432` is listening again.
2. If startup fails, inspect the configured cluster state and storage free space before retrying.
3. If the VM itself is unhealthy, recover the guest first and only then restart the database service.

## Escalation

If the service remains unreachable after 15 minutes, halt downstream writes and prepare to move into the ADR 0098 HA or backup-restore path when that workstream is available.

## Post-Incident

Document whether the failure was process, host, storage, or network related and record any recovery commands used.
