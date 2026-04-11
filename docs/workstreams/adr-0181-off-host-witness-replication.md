# Workstream ADR 0181: Off-Host Witness And Control Metadata Replication

- ADR: [ADR 0181](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0181-off-host-witness-and-control-metadata-replication.md)
- Title: Off-host witness bundle for recovery metadata
- Status: live_applied
- Branch: `codex/adr-0181-metadata-replication`
- Worktree: `../worktree-adr-0181-metadata-replication`
- Owner: codex
- Depends On: `adr-0051-control-plane-recovery`, `adr-0100-rto-rpo-targets`, `adr-0179-service-redundancy-tier-matrix`
- Conflicts With: none
- Shared Surfaces: control-plane recovery workflow, disaster recovery runbooks, release metadata, receipts

## Scope

- build a repo-managed witness bundle that captures recoverable control metadata without copying secret values
- publish that bundle to an immutable off-host archive only after verification succeeds
- require a matching remote git witness as part of the replication health check
- surface the resulting witness state in DR procedures and receipts

## Non-Goals

- configuring the real off-host storage mount in this repository change
- replacing PBS backups or the backup restore path
- introducing a second compute failure domain

## Expected Repo Surfaces

- `scripts/control_metadata_witness.py`
- `tests/test_control_metadata_witness.py`
- `playbooks/control-plane-recovery.yml`
- `inventory/group_vars/all.yml`
- `scripts/disaster_recovery_runbook.py`
- `scripts/generate_dr_report.py`
- `docs/runbooks/configure-control-plane-recovery.md`
- `docs/runbooks/disaster-recovery.md`
- `docs/adr/0181-off-host-witness-and-control-metadata-replication.md`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `receipts/witness-replication/`

## Expected Live Surfaces

- a versioned off-host archive path with immutable witness generations and a `latest` pointer
- a matching git remote ref for the applied branch or mainline commit
- witness-replication receipts that capture archive and remote verification outcomes
- DR operators can validate the witness bundle before restoring the host

## Verification

- `uv run --with pytest pytest -q tests/test_control_metadata_witness.py tests/test_disaster_recovery.py`
- `python3 scripts/control_metadata_witness.py sync --repo-root . --archive-root /tmp/lv3-witness --receipt-dir receipts/witness-replication-test --git-remote origin`
- `python3 scripts/control_metadata_witness.py verify --archive-root /tmp/lv3-witness`

## Merge Criteria

- the witness bundle includes repo truth plus locator metadata for recovery-critical secrets and restore procedures
- archive promotion keeps the previous `latest` generation intact when verification fails
- control-plane-recovery can publish and re-verify the latest off-host witness generation during a live apply

## Notes For The Next Assistant

- The live `main` replay succeeded on 2026-03-27 from commit `dca74443`, with `make converge-control-plane-recovery PLATFORM_TRACE_ID=adr0181main2` rerunning the runtime backup, restore drill, off-host witness publication, and witness verification end to end.
- The durable witness receipt for the merged replay is `receipts/witness-replication/20260327T103801Z-dca744432518-control-metadata-witness.json`, and the latest archive generation is `20260327T103801Z-dca744432518`.
- The git remote witness check remains intentionally strict: the selected remote ref must point at the same commit as local `HEAD`.
