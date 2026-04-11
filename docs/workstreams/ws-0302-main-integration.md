# Workstream ws-0302-main-integration

- ADR: [ADR 0302](../adr/0302-restic-for-encrypted-file-level-backup-of-platform-configuration-and-state-artifacts.md)
- Title: Integrate ADR 0302 Restic exact-main replay onto `origin/main`
- Status: live_applied
- Included In Repo Version: 0.177.115
- Platform Version Observed During Integration: 0.130.75
- Release Date: 2026-03-31
- Live Applied On: 2026-03-31
- Branch: `codex/ws-0302-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0302-main-integration`
- Owner: codex
- Depends On: `ws-0302-live-apply`

## Purpose

Carry the verified ADR 0302 Restic configuration-backup live apply onto the
latest unchanged `origin/main` baseline, cut the protected release and
canonical-truth surfaces from that synchronized tree, and publish the first
mainline repository and platform versions that record encrypted file-level
backup protection for repo-managed configuration and state artifacts.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0302-main-integration.md`
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
- `config/ansible-role-idempotency.yml`
- `config/correction-loops.json`
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
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `receipts/restic-backups/`
- `receipts/restic-restore-verifications/`
- `receipts/backup-coverage/`
- `receipts/restic-snapshots-latest.json`
- `receipts/live-applies/2026-03-31-adr-0302-restic-config-backup-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-31-ws-0302-*`

## Verification

- `git fetch origin --prune` confirmed that the newest realistic `origin/main`
  commit advanced to `51fc3a47358da12a272fe559a13e120e63a351b1`, carrying repo
  version `0.177.114` and platform version `0.130.74` before the final ADR
  0302 integration pass.
- The live platform proof remains the successful Restic interval backup receipt `receipts/restic-backups/20260331T060131Z.json`, the event-driven live-apply backup receipt `receipts/restic-backups/20260331T055348Z.json`, the restore-verification receipt `receipts/restic-restore-verifications/20260331T055701Z.json`, and the refreshed snapshot manifest `receipts/restic-snapshots-latest.json`.
- Repository automation passed on the integrated tree with `make syntax-check-restic-config-backup`, focused pytest for the Restic and ledger coverage, `make preflight WORKFLOW=restic-config-backup`, `make preflight WORKFLOW=restic-config-restore-verify`, `./scripts/validate_repo.sh workstream-surfaces agent-standards data-models`, `UV_PYTHON=python3.13 make validate`, and `UV_PYTHON=python3.13 make pre-push-gate`.
- The backup-coverage ledger still reports two unrelated uncovered assets, `monitoring` and `backup`, while confirming that the ADR 0302 Restic-backed assets are protected with current receipts and timestamps.

## Outcome

- Repository version `0.177.115` is the first integrated mainline version that records ADR 0302 as implemented.
- Platform version `0.130.75` is the first verified mainline platform version that records the Restic configuration-backup service as live.
- `receipts/live-applies/2026-03-31-adr-0302-restic-config-backup-mainline-live-apply.json` is the canonical mainline receipt for this ADR integration.
