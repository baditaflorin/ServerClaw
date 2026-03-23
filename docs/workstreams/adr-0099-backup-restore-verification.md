# Workstream ADR 0099: Automated Backup Restore Verification

- ADR: [ADR 0099](../adr/0099-automated-backup-restore-verification.md)
- Title: Weekly Windmill workflow restoring postgres-lv3, docker-runtime-lv3, and backup-lv3 into ephemeral VMs and running smoke tests
- Status: ready
- Branch: `codex/adr-0099-backup-restore-verification`
- Worktree: `../proxmox_florin_server-backup-restore-verification`
- Owner: codex
- Depends On: `adr-0020-backups`, `adr-0029-backup-vm`, `adr-0044-windmill`, `adr-0057-mattermost`, `adr-0066-audit-log`, `adr-0088-ephemeral-fixtures`, `adr-0097-alerting-routing`, `adr-0106-ephemeral-lifecycle`
- Conflicts With: none
- Shared Surfaces: `scripts/`, Windmill workflows, `receipts/` directory

## Scope

- write `scripts/restore_verification.py` — orchestrates PBS restore, smoke tests, and report writing for each target VM
- write `scripts/smoke_tests/postgres_smoke.py` — psycopg2-based Postgres connectivity and table-count tests
- write `scripts/smoke_tests/docker_runtime_smoke.py` — httpx-based health probe tests against restored Docker runtime containers
- write `scripts/smoke_tests/backup_vm_smoke.py` — PBS API connectivity test against restored backup VM
- write Windmill workflow `restore-verification` — scheduled Sunday 02:00 UTC; calls `scripts/restore_verification.py` via remote exec on build server
- create `receipts/restore-verifications/.gitkeep`
- add Grafana panel `Backup Health` to the platform overview dashboard (`config/grafana/dashboards/platform-overview.json`) showing last verification date and pass/fail per VM
- add Grafana alert: last successful verification > 10 days ago → warning alert
- add restore verification alert to `config/alertmanager/rules/platform.yml`

## Non-Goals

- Verifying all VMs (nginx and monitoring are stateless; their restore verification is lower priority)
- Continuous restore testing (weekly is sufficient)
- Testing PBS snapshots older than 7 days in this iteration

## Expected Repo Surfaces

- `scripts/restore_verification.py`
- `scripts/smoke_tests/postgres_smoke.py`
- `scripts/smoke_tests/docker_runtime_smoke.py`
- `scripts/smoke_tests/backup_vm_smoke.py`
- `config/grafana/dashboards/platform-overview.json` (patched: Backup Health panel)
- `config/alertmanager/rules/platform.yml` (patched: restore-verification-stale alert)
- `receipts/restore-verifications/.gitkeep`
- `docs/adr/0099-automated-backup-restore-verification.md`
- `docs/workstreams/adr-0099-backup-restore-verification.md`

## Expected Live Surfaces

- Windmill `restore-verification` workflow is scheduled and has at least one successful run
- `receipts/restore-verifications/` contains at least one report JSON
- Grafana platform overview shows Backup Health panel with green status
- Mattermost `#platform-ops` channel received the restore verification summary

## Verification

- Trigger workflow manually: `lv3 runbook restore-verification`
- Verify three ephemeral VMs appear in VMID range 900–909 during the workflow run
- Verify all three are destroyed after the workflow completes
- Read `receipts/restore-verifications/<date>.json`; verify `overall: pass` for all three VMs
- Verify Mattermost `#platform-ops` received the summary message

## Merge Criteria

- Workflow completes successfully with `overall: pass` for all three target VMs
- Ephemeral VMs are destroyed after the workflow (check `pct list` and `qm list` after run)
- Grafana panel shows last verification date = today (or date of the most recent run)
- Workflow is scheduled in Windmill for Sunday 02:00 UTC

## Notes For The Next Assistant

- PBS restore via API requires the `PBSClient` from `scripts/pbs_client.py` if it exists, or use `proxmoxer` with the backup node endpoint; check what PBS API credentials are available in OpenBao at `platform/pbs/api-token`
- The smoke test for `docker-runtime-lv3` must wait for all containers to start before probing; add a 90-second wait after VM boot before starting container health probes; some containers (Keycloak) take 60+ seconds to become ready
- The restored VMs will not have their OpenBao secrets available (they will attempt to connect to the live OpenBao using the same credentials — this is correct; test credentials are valid); if the restored VM's OpenBao connection fails, the smoke test should note this but not fail the overall test
- Ensure the `finally` block in `restore_verification.py` uses `proxmoxer` to destroy VMs by VMID even if the VMID is not in the expected list — guard against leaking VMs on unexpected exceptions
