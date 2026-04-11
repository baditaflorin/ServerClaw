# Backup Coverage Ledger

ADR 0271 turns backup coverage into a governed evidence surface instead of a
best-effort assumption.

The ledger reads the current Proxmox backup-job state, inspects the live PBS and
off-site storage listings, folds in the ADR 0302 Restic latest-snapshot receipt
for governed file-level backup sources, links those observations to the governed
backup sources already declared in `config/service-redundancy-catalog.json`, and
records the most recent successful restore-verification receipt when one exists.

## Entry Points

- `make backup-coverage-ledger`
- `uv run --with pyyaml python scripts/backup_coverage_ledger.py --write-receipt`
- Windmill worker wrapper: `python3 config/windmill/scripts/backup-coverage-ledger.py`
- receipts: `receipts/backup-coverage/*.json`

## What The Ledger Checks

1. Collect every governed Proxmox backup source already referenced by the
   service redundancy catalog:
   - `pbs_vm_<vmid>`
   - `proxmox_offsite_vm_<vmid>`
2. Collect every governed ADR 0302 Restic file-level source from
   `config/restic-file-backup-catalog.json`.
3. Resolve the VM-scoped source IDs to the live VM inventory on `proxmox-host`.
4. Query live Proxmox backup jobs through `pvesh get /cluster/backup`.
5. Query live backup artifacts through `pvesm list` on:
   - `lv3-backup-pbs`
   - the declared off-site storage from `config/disaster-recovery-targets.json`
6. Read `receipts/restic-snapshots-latest.json` for the newest Restic-backed
   configuration and receipt sources.
7. Mark each governed asset as:
   - `protected` when fresh backup evidence exists and a governed job covers it
   - `degraded` when fresh evidence exists but the governed job path is missing
   - `uncovered` when fresh evidence is missing entirely
8. Attach the latest successful restore-verification receipt for the same VM
   when ADR 0099 has already exercised that asset.

## Current Policy Meaning

- An `uncovered` asset is a policy failure and should be treated as a live
  recovery gap.
- A `degraded` asset still has recoverable evidence, but the governed job path
  has drifted and needs repair before the next failure.
- `make dr-status` now consumes the most recent backup-coverage receipt so
  uncovered assets appear directly in the DR readiness output.

## Verification

```bash
python3 -m py_compile scripts/backup_coverage_ledger.py config/windmill/scripts/backup-coverage-ledger.py
uv run --with pytest --with pyyaml pytest tests/test_backup_coverage_ledger.py tests/test_backup_coverage_ledger_windmill.py tests/test_disaster_recovery.py -q
uv run --with pyyaml python scripts/backup_coverage_ledger.py --format json
```

## Live Apply Notes

- The ledger is read-only on the platform. It does not mutate backup jobs or
  storage entries by itself.
- If the ledger reports an uncovered asset, repair the governed backup path
  first and then rerun `make backup-coverage-ledger` so the fresh receipt shows
  the corrected state.
- Restic-backed file-level assets use the latest receipt written by
  `scripts/restic_config_backup.py`; if those assets show as uncovered, rerun
  the ADR 0302 backup workflow first and then refresh the ledger.
- The current backup-of-backup contract is the off-site Proxmox copy of VM
  `160` (`backup`). Until `lv3-backup-offsite` exists live, ADR 0271 should
  continue to report `backup` as uncovered rather than pretending host-loss
  recovery is complete.
