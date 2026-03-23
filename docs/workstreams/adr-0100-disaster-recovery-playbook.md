# Workstream ADR 0100: RTO/RPO Targets and Disaster Recovery Playbook

- ADR: [ADR 0100](../adr/0100-rto-rpo-targets-and-disaster-recovery-playbook.md)
- Title: Formal RTO < 4h / RPO < 24h targets, ordered recovery sequence as Windmill runbook, and PBS off-site sync to Hetzner Storage Box
- Status: ready
- Branch: `codex/adr-0100-disaster-recovery`
- Worktree: `../proxmox_florin_server-disaster-recovery`
- Owner: codex
- Depends On: `adr-0020-backups`, `adr-0029-backup-vm`, `adr-0042-step-ca`, `adr-0043-openbao`, `adr-0051-control-plane-backup`, `adr-0094-developer-portal`, `adr-0098-postgres-ha`, `adr-0099-backup-restore-verification`
- Conflicts With: none
- Shared Surfaces: PBS config on `backup-lv3`, Windmill workflows, `docs/runbooks/`

## Scope

- write `scripts/disaster_recovery_runbook.py` — Windmill-compatible flow implementing Tier 0–5 recovery sequence
- write Windmill workflow `disaster-recovery-runbook` — wraps the script with step-level results and audit log recording
- write `docs/runbooks/disaster-recovery.md` — human-readable recovery playbook with all commands and expected outputs
- write `docs/runbooks/break-glass.md` — break-glass credential locations and emergency procedures (no actual credentials in the file; references to where they are stored)
- configure PBS off-site sync job to Hetzner Storage Box — add PBS remote sync configuration to `roles/backup_vm/` (or a new `backup_offsite_sync` role)
- add `config/disaster-recovery-targets.json` — machine-readable RTO/RPO targets per scenario
- write `scripts/generate_dr_report.py` — reads the targets and last restore verification reports to produce a current DR readiness score
- add `make dr-status` target — runs `generate_dr_report.py` and prints readiness
- add `lv3 release status` to show DR table-top review status as one of the 1.0.0 criteria (ADR 0110 integration)

## Non-Goals

- Automated disaster recovery execution (recovery is always operator-initiated; the runbook is a guide and executor, not an auto-healer)
- Active-standby replication to a second Hetzner server
- RTO/RPO SLAs for individual services (covered by ADR 0096 SLOs)

## Expected Repo Surfaces

- `scripts/disaster_recovery_runbook.py`
- `config/disaster-recovery-targets.json`
- `scripts/generate_dr_report.py`
- `docs/runbooks/disaster-recovery.md`
- `docs/runbooks/break-glass.md`
- `roles/backup_vm/` or `roles/backup_offsite_sync/` (patched or new: PBS remote sync config)
- Makefile (patched: `make dr-status`)
- `docs/adr/0100-rto-rpo-targets-and-disaster-recovery-playbook.md`
- `docs/workstreams/adr-0100-disaster-recovery.md`

## Expected Live Surfaces

- PBS off-site sync job is configured and has at least one successful sync to the Hetzner Storage Box
- Windmill `disaster-recovery-runbook` workflow is visible in Windmill UI (not yet scheduled; on-demand only)
- `make dr-status` exits 0 and prints a DR readiness summary
- `docs.lv3.org/runbooks/disaster-recovery/` renders the playbook (requires ADR 0094 to be deployed)

## Verification

- `make dr-status` shows: RTO target < 4h, RPO target < 24h, last restore verification pass, off-site sync last run date
- Check PBS UI on `backup-lv3`: remote sync job shows at least one successful job to the Hetzner Storage Box
- Verify `disaster-recovery-runbook` Windmill workflow can be started and that Tier 1 step completes successfully (restore a single PBS snapshot to a test VM and verify step-ca is contactable)
- Read `docs/runbooks/disaster-recovery.md`; every command in the document is executable against the live platform

## Merge Criteria

- PBS off-site sync job is configured and working
- `docs/runbooks/disaster-recovery.md` covers all 5 recovery tiers with specific commands
- `make dr-status` works and reports correct current state
- Windmill workflow Tier 1 step tested successfully

## Notes For The Next Assistant

- Hetzner Storage Box credentials: set up a new Storage Box in the Hetzner Robot panel, enable SFTP access, store credentials in OpenBao at `platform/hetzner/storage-box/credentials`
- PBS remote sync is configured in the PBS web UI under Datastore → Remote → Add; the remote type is `PBS Remote` if syncing to another PBS, or `SFTP` for the Storage Box; verify which is appropriate for the Storage Box model
- The `disaster-recovery-runbook.py` Windmill flow should use `@windmill_step` decorators with explicit names matching the Tier N terminology in the ADR; this makes the Windmill UI readable during an actual recovery
- The `break-glass.md` runbook must NOT contain actual credentials; it must reference locations (OpenBao paths, physical card location) only; a test reviewer should verify no secrets appear in the file before merge
