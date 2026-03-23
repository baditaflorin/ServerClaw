# Backup Restore Verification

ADR 0099 adds a repository-managed restore verification workflow that restores the highest-risk PBS-protected guests into the staging bridge, runs smoke tests, writes a receipt, and tears the restored VMs down unconditionally.

## Entry Points

- local run: `make restore-verification`
- direct script: `python3 scripts/restore_verification.py`
- Windmill worker wrapper: `python3 config/windmill/scripts/restore-verification.py`
- receipts: `receipts/restore-verifications/*.json`

## Targets

The current repository implementation verifies three guests:

- `postgres-lv3` restored to VMID `900`
- `docker-runtime-lv3` restored to VMID `901`
- `backup-lv3` restored to VMID `902`

Each restore uses the staging bridge and IP assignments already defined for the ADR 0088 fixture network:

- `docker-runtime-lv3` -> `10.20.10.100/24`
- `postgres-lv3` -> `10.20.10.110/24`
- `backup-lv3` -> `10.20.10.120/24`

## Workflow

1. Query `sudo pvesm list lv3-backup-pbs` on the Proxmox host.
2. Select one backup per target from the last 7 days.
3. Restore the backup into VMIDs `900` to `902`.
4. Rewire the restored guest to `vmbr20`, keep the original MAC, refresh cloud-init, and boot it.
5. Wait for SSH through the Proxmox jump path.
6. Run guest-local smoke tests.
7. Write one JSON receipt under `receipts/restore-verifications/`.
8. Emit the mutation-audit event and optional NATS plus Mattermost notifications.
9. Destroy the restored VMs even when an earlier step fails.

## Smoke Tests

### postgres-lv3

- `pg_isready` on localhost
- one `psql` table-count query per managed database
- one `pg_dump --schema-only` per managed database

### docker-runtime-lv3

- Keycloak readiness endpoint from the local guest
- NetBox readiness endpoint from the local guest
- Windmill readiness endpoint from the local guest
- OpenBao readiness endpoint as a non-blocking observation

### backup-lv3

- TCP reachability on `127.0.0.1:8007`
- `proxmox-backup-manager datastore list --output-format json`

## Optional Outputs

If these variables are present when the workflow runs, the script also writes summary metrics for the managed Grafana platform overview dashboard:

- `RESTORE_VERIFICATION_INFLUXDB_URL`
- `RESTORE_VERIFICATION_INFLUXDB_BUCKET`
- `RESTORE_VERIFICATION_INFLUXDB_ORG`
- `RESTORE_VERIFICATION_INFLUXDB_TOKEN`

If this variable is present, the workflow posts the summary to Mattermost:

- `RESTORE_VERIFICATION_MATTERMOST_WEBHOOK`

If `--publish-nats` is set, the workflow emits:

- `platform.backup.restore-verification.completed`
- `platform.backup.restore-verification.failed` when any target fails

## Verification

- `python3 -m py_compile scripts/restore_verification.py scripts/smoke_tests/postgres_smoke.py scripts/smoke_tests/docker_runtime_smoke.py scripts/smoke_tests/backup_vm_smoke.py config/windmill/scripts/restore-verification.py`
- `uv run --with pytest --with pyyaml pytest tests/test_restore_verification.py tests/test_restore_verification_windmill.py -q`
- `python3 scripts/restore_verification.py --help`

## Live Rollout Notes

- The repository implementation is designed to run from `main` once the staging bridge remains available on `vmbr20`.
- The current repo does not ship a checked-in Prometheus or Alertmanager rule surface, so the stale-verification signal is currently exposed through Influx-backed Grafana status panels rather than a committed alert-rule file.
