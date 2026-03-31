# Workstream ws-0302-live-apply: ADR 0302 Live Apply From Latest `origin/main`

- ADR: [ADR 0302](../adr/0302-restic-for-encrypted-file-level-backup-of-platform-configuration-and-state-artifacts.md)
- Title: deploy Restic-backed encrypted file-level backups for platform configuration and state artifacts
- Status: ready_to_merge
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
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/restic_config_backup/`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `playbooks/restic-config-backup.yml`
- `config/windmill/scripts/restic-config-backup.py`
- `scripts/restic_config_backup.py`
- `scripts/trigger_restic_live_apply.py`
- `scripts/backup_coverage_ledger.py`
- `tests/test_restic_config_backup.py`
- `tests/test_restic_config_backup_role.py`
- `tests/test_restic_config_backup_windmill.py`
- `tests/test_backup_coverage_ledger.py`
- `receipts/restic-backups/`
- `receipts/restic-restore-verifications/`
- `receipts/backup-coverage/`
- `receipts/restic-snapshots-latest.json`
- `receipts/live-applies/`

## Expected Live Surfaces

- `lv3-restic-config-backup.timer` active on `docker-runtime-lv3`
- MinIO bucket `restic-config-backup` present with Object Lock and versioning
- successful backup and restore-verification receipts under the mirrored worker checkout
- `receipts/restic-snapshots-latest.json` synced into the branch and consumed by the backup-coverage ledger

## Verification

- `make restic-config-backup env=production` passed after the final runner fixes and produced `receipts/restic-backups/20260331T060131Z.json` plus the refreshed `receipts/restic-snapshots-latest.json`.
- `make restic-config-restore-verify env=production` passed and produced `receipts/restic-restore-verifications/20260331T055701Z.json`.
- The event-driven live-apply backup path for `config/` and `versions/stack.yaml` passed via manual worker sync and produced `receipts/restic-backups/20260331T055348Z.json`.
- `sudo systemctl start lv3-restic-config-backup.service` completed with `Result=success`, and `lv3-restic-config-backup.timer` is active and enabled on `docker-runtime-lv3`.
- `mc version info local/restic-config-backup` reported that MinIO versioning is enabled for the Restic bucket.
- Repo-side validation passed with `make syntax-check-restic-config-backup`, focused pytest `17 passed`, `./scripts/validate_repo.sh workstream-surfaces agent-standards`, both `make preflight` workflows, and `make backup-coverage-ledger`.

## Notes

- A concurrent, unrelated Windmill checkout refresh on `docker-runtime-lv3` intermittently removed `/srv/proxmox_florin_server` files during verification. The final live apply therefore includes explicit evidence of temporary manual syncs for the new Restic runner and catalog before the successful event-driven backup.
- The final backup coverage ledger still shows unrelated pre-existing gaps for `monitoring-lv3` and `backup-lv3`; those are outside ADR 0302 and remain visible rather than being masked by this workstream.
