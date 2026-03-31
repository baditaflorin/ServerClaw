# Workstream ws-0302-live-apply: ADR 0302 Live Apply From Latest `origin/main`

- ADR: [ADR 0302](../adr/0302-restic-for-encrypted-file-level-backup-of-platform-configuration-and-state-artifacts.md)
- Title: deploy Restic-backed encrypted file-level backups for platform configuration and state artifacts
- Status: in_progress
- Branch: `codex/ws-0302-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0302-live-apply`
- Owner: codex
- Depends On: `adr-0029`, `adr-0034`, `adr-0043`, `adr-0271`, `adr-0274`, `adr-0276`, `adr-0299`
- Conflicts With: none

## Scope

- add the repo-managed ADR 0302 Restic backup role, scripts, catalogs, Windmill seeding, and backup-coverage integration
- live-apply the timer, runtime credential bundle, bucket bootstrap, backup run, and restore verification on `docker-runtime-lv3`
- preserve merge-safe documentation, receipts, and ADR metadata so the final exact-main replay can integrate cleanly

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0302-live-apply.md`
- `docs/adr/0302-restic-for-encrypted-file-level-backup-of-platform-configuration-and-state-artifacts.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/restic-config-backups.md`
- `docs/runbooks/backup-coverage-ledger.md`
- `.config-locations.yaml`
- `Makefile`
- `config/restic-file-backup-catalog.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/event-taxonomy.yaml`
- `config/ansible-execution-scopes.yaml`
- `config/controller-local-secrets.json`
- `collections/ansible_collections/lv3/platform/roles/restic_config_backup/`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `playbooks/restic-config-backup.yml`
- `config/windmill/scripts/restic-config-backup.py`
- `scripts/restic_config_backup.py`
- `scripts/trigger_restic_live_apply.py`
- `scripts/backup_coverage_ledger.py`
- `tests/test_restic_config_backup.py`
- `tests/test_restic_config_backup_windmill.py`
- `tests/test_backup_coverage_ledger.py`
- `receipts/restic-backups/`
- `receipts/restic-restore-verifications/`
- `receipts/restic-snapshots-latest.json`
- `receipts/live-applies/`

## Expected Live Surfaces

- `lv3-restic-config-backup.timer` active on `docker-runtime-lv3`
- MinIO bucket `restic-config-backup` present with Object Lock and versioning
- successful backup and restore-verification receipts under the mirrored worker checkout
- `receipts/restic-snapshots-latest.json` synced into the branch and consumed by the backup-coverage ledger
