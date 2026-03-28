# Seed Data Snapshots

ADR 0187 adds deterministic anonymized seed snapshots so repeatable tests can stage the same `tiny`, `standard`, or `recovery` dataset shape without copying live credentials or personal data.

## Repo Surfaces

- catalog: [`config/seed-data-catalog.json`](../../config/seed-data-catalog.json)
- builder and publisher: [`scripts/seed_data_snapshots.py`](../../scripts/seed_data_snapshots.py)
- fixture staging: [`scripts/fixture_manager.py`](../../scripts/fixture_manager.py)
- restore verification staging: [`scripts/restore_verification.py`](../../scripts/restore_verification.py)
- backup VM store: [`collections/ansible_collections/lv3/platform/roles/backup_vm/tasks/main.yml`](../../collections/ansible_collections/lv3/platform/roles/backup_vm/tasks/main.yml)

## Build And Verify

```bash
make seed-snapshot-build SEED_CLASS=tiny
make seed-snapshot-verify SEED_CLASS=tiny
make seed-snapshot-list
```

The builder creates a deterministic local snapshot under `.local/seed-data/snapshots/<class>/<snapshot-id>/` and writes:

- `manifest.json`
- `identities.ndjson`
- `sessions.ndjson`
- `workflow_runs.ndjson`
- `messages.ndjson`
- `assets.ndjson`
- `audit_events.ndjson`

The catalog points at the controller-local salt file declared in `config/controller-local-secrets.json`. The builder creates that file automatically if it does not exist.

## Publish To `backup-lv3`

```bash
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make configure-backup-vm
make seed-snapshot-publish SEED_CLASS=tiny
python3 scripts/seed_data_snapshots.py verify --seed-class tiny --remote
```

Published snapshots land under `/var/lib/lv3/seed-data-snapshots/<class>/<snapshot-id>/` on `backup-lv3`.

## Use In Fixtures

```bash
python3 scripts/fixture_manager.py create ops-base --purpose adr-0187-check --policy integration-test --seed-class tiny
```

The fixture manager stages the selected snapshot under `/var/lib/lv3-seed-data/<receipt-id>/` inside the guest and records the staged snapshot id in the fixture receipt.

## Use In Restore Verification

```bash
python3 scripts/restore_verification.py --seed-class standard
```

When a seed class is provided, each restored VM receives the selected snapshot under `/var/lib/lv3-seed-data/restore-verification/<vm-name>/` before smoke tests run. The receipt records the seed class, snapshot id, and remote path per target.
