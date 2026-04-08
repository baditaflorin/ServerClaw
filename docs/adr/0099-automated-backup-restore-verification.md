# ADR 0099: Automated Backup Restore Verification

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.99.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

The platform has a backup VM (`backup-lv3`, VMID 160) running Proxmox Backup Server (PBS) that takes nightly VM snapshots of all managed guests (ADR 0020). Snapshots are verified at the block-device level by PBS itself (chunk integrity). However, block-device integrity is not the same as application-level recoverability. A backup that is block-intact may still be unrestorable if:

- The filesystem inside the snapshot is corrupted
- The Postgres cluster has an unclean shutdown state that requires manual recovery
- A configuration file was corrupted before the snapshot was taken
- The PBS restore procedure fails due to a disk space or network issue

The only way to prove a backup is restorable is to restore it. Until a backup is restored and the restored service is verified to be functional, the backup is a hypothesis, not a guarantee.

Currently, no restore testing exists. The backup strategy is entirely untested beyond PBS's own chunk verification. Operators assume backups work. This assumption has no evidence to support it.

## Decision

We will implement a **weekly automated restore verification** workflow that restores the three most critical VM backups into ephemeral infrastructure fixtures (ADR 0088) on the staging network, runs smoke tests against the restored services, records the outcome in the mutation audit log (ADR 0066), and sends a summary to Mattermost (ADR 0057).

### Verification scope

The three most critical VMs are selected for weekly restore testing:

| VM | Why critical | Smoke test |
|---|---|---|
| `postgres-lv3` | Backing store for 5 services; most complex recovery | Postgres starts; all five databases are accessible; pg_dump of each DB succeeds |
| `docker-runtime-lv3` | Runs all platform control plane services | Keycloak, OpenBao, Windmill, NetBox containers start; health probes return 200 |
| `backup-lv3` | PBS itself; backing up the backup server is essential | PBS starts; the most recent job list is queryable |

The nginx VM and monitoring VM are lower priority for restore testing since they are stateless (configuration is fully reproducible from the repo) and do not hold user data.

### Workflow design

The verification workflow runs as a Windmill scheduled flow every Sunday at 02:00 UTC (within the platform's low-traffic window):

```
1. Select a random backup from the last 7 days for each target VM
   (random selection exercises different days' backups over time)

2. For each target VM:
   a. Restore the backup to a temporary VMID (900+) on vmbr20 (staging network)
   b. Wait for the VM to boot and pass its basic health probe (timeout: 5 min)
   c. Run service-specific smoke tests (see below)
   d. Record: start time, end time, backup date selected, test results, any errors
   e. Destroy the temporary VM unconditionally (even on test failure)

3. Aggregate results into a restore verification report
4. Write report to receipts/restore-verifications/<date>.json
5. Post summary to Mattermost #platform-ops
6. Emit NATS event platform.backup.restore-verification.completed
7. If any test failed: emit platform.backup.restore-verification.failed → Alertmanager critical alert
```

### Smoke tests

**postgres-lv3 smoke tests** (run via `psql` from the build server against the restored VM's IP):

```python
def smoke_test_postgres(restored_ip: str) -> list[TestResult]:
    results = []
    for db in ["keycloak", "mattermost", "netbox", "openbao", "windmill"]:
        try:
            conn = psycopg2.connect(host=restored_ip, dbname=db, user="postgres",
                                    password=get_secret("postgres/restore-test-password"))
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM information_schema.tables")
            count = cur.fetchone()[0]
            results.append(TestResult(db=db, status="pass", table_count=count))
        except Exception as e:
            results.append(TestResult(db=db, status="fail", error=str(e)))
    return results
```

**docker-runtime-lv3 smoke tests** (health probes against the restored VM's container ports):

```python
SERVICES_TO_CHECK = [
    ("keycloak", 8080, "/health/ready"),
    ("openbao", 8200, "/v1/sys/health"),
    ("netbox", 8004, "/api/"),
    ("windmill", 8005, "/api/v1/ping"),
]

def smoke_test_docker_runtime(restored_ip: str) -> list[TestResult]:
    return [probe_http(restored_ip, port, path) for name, port, path in SERVICES_TO_CHECK]
```

### Ephemeral VM lifecycle

Restored VMs use VMID range 900–909 (reserved for restore tests). The workflow ensures these VMIDs are always destroyed at the end of the workflow, even on failure, using a `finally` block:

```python
restored_vmids = []
try:
    vmid = restore_vm_backup(source_vmid=150, target_vmid=900, network="vmbr20")
    restored_vmids.append(vmid)
    results = run_smoke_tests(vmid)
finally:
    for vmid in restored_vmids:
        destroy_vm(vmid)  # always clean up
```

### Restore verification report schema

```json
{
  "schema_version": "1.0",
  "run_date": "2026-03-29T02:00:00Z",
  "triggered_by": "windmill-schedule",
  "results": [
    {
      "vm": "postgres-lv3",
      "source_vmid": 150,
      "backup_date": "2026-03-27",
      "restore_duration_seconds": 187,
      "boot_time_seconds": 43,
      "tests": [
        {"name": "keycloak_db_accessible", "status": "pass"},
        {"name": "mattermost_db_accessible", "status": "pass"},
        {"name": "netbox_db_accessible", "status": "pass"},
        {"name": "openbao_db_accessible", "status": "pass"},
        {"name": "windmill_db_accessible", "status": "pass"}
      ],
      "overall": "pass"
    }
  ],
  "summary": "3/3 VMs passed restore verification",
  "overall": "pass"
}
```

### Grafana panel

The monitoring dashboard includes a **Backup Health** panel showing:
- Last successful restore verification date (should be ≤ 7 days ago)
- Pass/fail status per VM from the most recent report
- A Grafana alert fires if the last successful verification is older than 10 days (workflow may have silently failed)

### Mattermost notification

```
✅ Restore verification completed (2026-03-29)
• postgres-lv3: PASS (backup from 2026-03-27, restore: 3m7s)
• docker-runtime-lv3: PASS (backup from 2026-03-26, restore: 5m12s)
• backup-lv3: PASS (backup from 2026-03-28, restore: 1m43s)
All backups are verified restorable. Receipt: receipts/restore-verifications/2026-03-29.json
```

### Handling test failures

A test failure means the backup is not reliably restorable. The response is:
1. A Grafana critical alert fires and routes to Ntfy (ADR 0097)
2. The operator investigates using the restore verification report
3. If the failure is reproducible (same VM fails twice in a row), the relevant PBS job is reconfigured and a fresh backup is taken and verified manually
4. The incident is recorded in the mutation audit log (ADR 0066)

## Consequences

**Positive**
- Backup strategy is validated weekly with evidence; "our backups work" changes from an assumption to a measured fact
- Failures are detected during a low-traffic window (Sunday 02:00) rather than during an actual disaster recovery attempt
- The restore verification report provides an auditable history of backup health; useful for understanding whether a sudden failure is a recent regression or a longstanding issue
- Ephemeral VM cleanup (even on failure) ensures test VMs never accumulate and consume production resources

**Negative / Trade-offs**
- A restore + smoke test of three VMs consumes approximately 30 minutes and significant I/O on the Proxmox host; this must be scheduled during the low-traffic window and must not run concurrently with other backup jobs
- The restore process copies VM data from PBS to local storage temporarily; sufficient local disk space must be reserved for three concurrent restored VMs (~240 GB total during the test window)
- Writing and maintaining smoke tests is ongoing work; they must be updated when services change their health endpoints or database names

## Alternatives Considered

- **PBS chunk integrity check only**: what PBS already does; proves data is intact at the block level but not that the service can start from that data
- **Annual manual restore drill**: common in enterprise; insufficient verification cadence; a year-old backup strategy may have been silently broken for months
- **Continuous restore testing (every night)**: more thorough but doubles the nightly I/O burden; weekly is the right balance for a homelab

## Related ADRs

- ADR 0020: Storage and backup model (PBS backups are the source for this workflow)
- ADR 0029: Backup VM baseline (PBS runs on `backup-lv3`)
- ADR 0057: Mattermost (restore verification summary destination)
- ADR 0066: Mutation audit log (verification results are recorded here)
- ADR 0088: Ephemeral infrastructure fixtures (restored VMs use this mechanism)
- ADR 0097: Alerting routing (failure alerts route through this model)
- ADR 0100: Disaster recovery playbook (this workflow validates the recovery path)
