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
4. The minimal worker-checkout support files required by the timer and manual
   entrypoints.
5. The MinIO bucket `restic-config-backup` with Object Lock and versioning.

When `docker-runtime-lv3` has gone through a broad Docker recovery, the shared
`minio` container may exist but remain stopped. The repo-managed converge task
and live-apply trigger now treat that as recoverable and start the container
before bucket bootstrap or Restic endpoint discovery instead of failing on the
stale `invalid IP` inspect result.

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
- `python3 /srv/proxmox_florin_server/scripts/restic_config_backup.py --repo-root /srv/proxmox_florin_server --mode restore-verify --credential-file /run/lv3-systemd-credentials/restic-config-backup/runtime-config.json`
- Confirm `receipts/restic-snapshots-latest.json` shows the latest source state.
- Confirm `make backup-coverage-ledger` reports the ADR 0302 file-level assets.

## Notes

- The manual, timer, and Windmill paths all execute the mirrored worker checkout
  at `/srv/proxmox_florin_server`. The converge role and live-apply trigger
  stage the minimal backup support files there before validation runs, but the
  broader worker checkout should still be kept current for ongoing scheduled use.
- The MinIO endpoint is resolved from the live shared `minio` container IP
  instead of assuming a host-published port.
- Stale notifications are best-effort: NATS publication and ntfy delivery are
  recorded in the backup receipt, but a notification failure does not discard a
  successful Restic snapshot receipt.
- If a backup run is interrupted and the next replay reports `repository is
  already locked`, confirm the named PID on `docker-runtime-lv3` is gone and
  then clear the stale repository lock with `restic unlock` before retrying the
  managed workflow.
- If the shared MinIO layer or the Restic path starts hanging after a broader
  Docker-runtime recovery, check `/` headroom on `docker-runtime-lv3` and
  follow [docker-runtime-disk-pressure.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0274-mainline-refresh-v6/docs/runbooks/docker-runtime-disk-pressure.md)
  before replaying the managed backup or MinIO live-apply wrapper.
