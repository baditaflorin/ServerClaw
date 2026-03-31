# Release 0.177.115

- Date: 2026-03-31

## Summary
- Implemented ADR 0302 encrypted Restic file-level backups for platform configuration and state artifacts, including the MinIO-backed repository, systemd timer convergence, live-apply-trigger coverage for `config/` and `versions/stack.yaml`, restore verification receipts, and backup-coverage ledger integration.

## Platform Impact
- ADR 0302 is now live on production: docker-runtime-lv3 writes encrypted Restic file-level backups into the MinIO-backed restic-config-backup repository and the managed backup plus restore verification paths are now evidenced in-repo.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
