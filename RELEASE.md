# Release 0.108.0

- Date: 2026-03-24

## Summary
- implemented ADR 0115 in the repository with the `ledger.events` Postgres migration, the `platform.ledger` writer/reader/replay package, the `windmill/ledger/migrate-audit-log.py` migration helper, and optional dual-write from `scripts/mutation_audit.py` when `LV3_LEDGER_DSN` is configured
- added the mutation-ledger operator runbook, registered the ADR 0115 workstream in `workstreams.yaml`, and marked ADR 0115 plus its workstream as implemented in repo version `0.108.0`

## Platform Impact
- no live platform version bump; this release updates repository automation, release metadata, and operator tooling only

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
