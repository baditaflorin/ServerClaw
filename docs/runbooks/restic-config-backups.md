# Restic Config Backups

ADR 0302 adds an encrypted file-level backup path for platform configuration and
receipt artifacts on `docker-runtime-lv3` using Restic and the existing MinIO
runtime.

## Entry Points

- `make syntax-check-restic-config-backup`
- `make converge-restic-config-backup env=production`
- `make restic-config-backup env=production`
- `make restic-config-restore-verify env=production`
- Windmill script: `python3 config/windmill/scripts/restic-config-backup.py`
- receipts:
  - `receipts/restic-backups/*.json`
  - `receipts/restic-restore-verifications/*.json`
  - `receipts/restic-snapshots-latest.json`

## Governed Sources

- `receipts/` every 6 hours
- `config/` on successful live apply
- `versions/stack.yaml` on successful live apply
- `config/controller-local-secrets.json` daily
- `config/falco/` on successful live apply when that optional path exists

## What Converge Installs

1. The `restic` package on `docker-runtime-lv3`.
2. An OpenBao-backed runtime credential bundle at
   `/run/lv3-systemd-credentials/restic-config-backup/runtime-config.json`.
3. The `lv3-restic-config-backup.service` and `lv3-restic-config-backup.timer`
   systemd units.
4. The MinIO bucket `restic-config-backup` with Object Lock and versioning.

When `docker-runtime-lv3` has gone through a broad Docker recovery, `outline-minio`
may exist but remain stopped. The repo-managed converge task and live-apply trigger
now treat that as recoverable and start the container before bucket bootstrap or
Restic endpoint discovery instead of failing on the stale `invalid IP` inspect
result.

## Verification

```bash
python3 -m py_compile scripts/restic_config_backup.py scripts/trigger_restic_live_apply.py config/windmill/scripts/restic-config-backup.py scripts/backup_coverage_ledger.py
python3 -m json.tool config/restic-file-backup-catalog.json
uv run --with pytest --with pyyaml pytest tests/test_restic_config_backup.py tests/test_restic_config_backup_windmill.py tests/test_backup_coverage_ledger.py tests/test_backup_coverage_ledger_windmill.py tests/test_disaster_recovery.py -q
make syntax-check-restic-config-backup
make converge-restic-config-backup env=production
make converge-windmill env=production
make restic-config-backup env=production
make restic-config-restore-verify env=production
make backup-coverage-ledger
```

## Live Checks

- `systemctl status lv3-restic-config-backup.timer --no-pager`
- `systemctl start lv3-restic-config-backup.service`
- `make restic-config-restore-verify env=production`
- Confirm `receipts/restic-snapshots-latest.json` shows the latest source state.
- Confirm `make backup-coverage-ledger` reports the ADR 0302 file-level assets.

## Notes

- The host-side service, live-apply trigger, and Windmill wrapper keep
  `/srv/proxmox_florin_server` as the backup source of truth, but they now
  fall back to `/opt/api-gateway/service/scripts/restic_config_backup.py` and
  `/etc/lv3/restic-config-backup/restic-file-backup-catalog.json` when the
  worker checkout mirror is missing ADR 0302's executable or catalog surface.
- `make converge-restic-config-backup env=production` now auto-starts the
  shared `outline-minio` container when it exists but was left stopped after
  Docker/runtime recovery.
- The MinIO endpoint is resolved from the live `outline-minio` container IP
  instead of assuming a host-published port.
- Stale notifications are best-effort: NATS publication and ntfy delivery are
  recorded in the backup receipt, but a notification failure does not discard a
  successful Restic snapshot receipt.
