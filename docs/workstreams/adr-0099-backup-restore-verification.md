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

- write `scripts/restore_verification.py` — orchestrates PBS restore, smoke tests, receipt writing, mutation audit emission, and optional NATS plus Mattermost notifications
- write `scripts/smoke_tests/postgres_smoke.py` — guest-local PostgreSQL readiness, table-count, and `pg_dump` smoke tests
- write `scripts/smoke_tests/docker_runtime_smoke.py` — guest-local HTTP health probes for the restored Docker runtime services
- write `scripts/smoke_tests/backup_vm_smoke.py` — guest-local PBS CLI and listener checks on the restored backup VM
- write Windmill workflow wrapper `restore-verification` — runs `scripts/restore_verification.py` from the mounted repo checkout
- create `receipts/restore-verifications/.gitkeep`
- add `make restore-verification`
- add workflow catalog entry for `restore-verification`
- add a runbook at `docs/runbooks/backup-restore-verification.md`
- add Grafana `Backup Restore` status panels to the platform overview dashboard template via Influx-backed summary metrics

## Non-Goals

- Verifying all VMs (nginx and monitoring are stateless; their restore verification is lower priority)
- Continuous restore testing (weekly is sufficient)
- Testing PBS snapshots older than 7 days in this iteration

## Expected Repo Surfaces

- `scripts/restore_verification.py`
- `scripts/smoke_tests/postgres_smoke.py`
- `scripts/smoke_tests/docker_runtime_smoke.py`
- `scripts/smoke_tests/backup_vm_smoke.py`
- `config/windmill/scripts/restore-verification.py`
- `config/workflow-catalog.json`
- `Makefile`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/templates/_grafana_dashboard_macros.j2`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/templates/lv3-platform-overview.json.j2`
- `receipts/restore-verifications/.gitkeep`
- `docs/runbooks/backup-restore-verification.md`
- `docs/adr/0099-automated-backup-restore-verification.md`
- `docs/workstreams/adr-0099-backup-restore-verification.md`

## Expected Live Surfaces

- Windmill `restore-verification` workflow is scheduled and has at least one successful run
- `receipts/restore-verifications/` contains at least one report JSON
- Grafana platform overview shows Backup Health panel with green status
- Mattermost `#platform-ops` channel received the restore verification summary

## Verification

- Trigger the repo workflow manually: `make restore-verification`
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

- The current implementation restores through the Proxmox host CLI over SSH instead of calling the PVE or PBS HTTP APIs directly. This keeps the workflow aligned with the repo's existing host-side PBS operations and avoids a second credentials path.
- The smoke test for `docker-runtime-lv3` waits 90 seconds after SSH readiness before probing the service endpoints because Keycloak is the slowest runtime to settle after restore.
- OpenBao remains a non-blocking observation in the Docker runtime smoke suite. A restored Docker runtime can still be judged pass if the required services recover while the OpenBao readiness probe reports a soft failure.
- The repository does not currently ship a committed Prometheus or Alertmanager rule surface, so stale restore-verification age is exposed through Influx-backed Grafana status panels for now.

## Outcome

- repository implementation is complete on the ADR 0099 workstream branch with the restore-verification script, smoke-test helpers, Windmill wrapper, workflow catalog entry, runbook, receipt directory, dashboard summary metrics, and targeted tests
- live rollout still requires enabling the workflow from `main`, verifying the staging bridge path on the Proxmox host, and confirming the external notification variables in the execution environment
