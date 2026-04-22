# Data Retention

## Purpose

This runbook defines the repository-managed data retention controls introduced by ADR 0103.

## Canonical Sources

- ADR: [docs/adr/0103-data-classification-and-retention-policy.md](../adr/0103-data-classification-and-retention-policy.md)
- data catalog: [config/data-catalog.json](../../config/data-catalog.json)
- schema: [docs/schema/data-catalog.schema.json](../schema/data-catalog.schema.json)
- purge tool: [scripts/purge_old_receipts.py](../../scripts/purge_old_receipts.py)
- decommission helper: [scripts/decommission_service.py](../../scripts/decommission_service.py)
- scheduled runtime role: [roles/data_retention](../../roles/data_retention)

## What Is Enforced

- Loki log retention is pinned to 30 days.
- Tempo trace retention is pinned to 14 days.
- Grafana annotations are capped at 90 days.
- Mattermost retention is configured for 2 years through `DataRetentionSettings`.
- NetBox changelog retention is configured for 180 days and enforced via scheduled housekeeping.
- Receipt directories and the JSONL mutation-audit sink can be pruned from the catalog-driven retention policy.
- Repository validation rejects tracked `.env` files and validates the data catalog schema.

## Validate The Catalog

```bash
python3 scripts/data_catalog.py --validate
python3 scripts/validate_repository_data_models.py --validate
```

## Preview Receipt And Audit Cleanup

```bash
python3 scripts/purge_old_receipts.py
```

By default this is a dry run. It reads retention windows from `config/data-catalog.json`, scans `receipts/`, and reports which files or audit-log lines would be removed.

## Execute Cleanup

```bash
python3 scripts/purge_old_receipts.py --execute
```

Optional overrides:

- `--receipts-root /path/to/receipts`
- `--audit-log /path/to/mutation-audit.jsonl`
- `--catalog /path/to/data-catalog.json`

## Deploy Scheduled Cleanup

Apply the runtime scheduler on the Docker runtime guest:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/data-retention.yml
```

That role installs the canonical purge script and catalog onto the target, then enables `lv3-data-retention.timer`.

## Decommission A Service

Preview the structural cleanup plan:

```bash
python3 scripts/platform_ops.py decommission-preview --service netbox
python3 scripts/decommission_service.py --service netbox --validate-registry
```

Both commands print machine-readable JSON on stdout. `--validate-registry`
writes human status to stderr and should report an empty `registry_warnings`
list before destructive cleanup.

Execute destructive runtime cleanup:

```bash
LV3_POSTGRES_ADMIN_DSN='postgresql://postgres:...@database.example.com/postgres' \
OPENBAO_ADDR='https://openbao.lv3.internal' \
OPENBAO_TOKEN='...' \
KEYCLOAK_ADMIN_TOKEN='...' \
python3 scripts/decommission_service.py \
  --service netbox \
  --execute \
  --confirm netbox \
  --loki-url http://127.0.0.1:3100 \
  --keycloak-url https://sso.example.com
```

Execute deterministic code cleanup from a clean branch:

```bash
python3 scripts/decommission_service.py \
  --service netbox \
  --purge-code \
  --confirm netbox \
  --validate-registry
```

The code purge removes registered catalog entries structurally, removes
`# BEGIN SERVICE:` / `# END SERVICE:` blocks from generated Prometheus assets,
regenerates derived SLO and HTTPS/TLS files, and parses modified JSON/YAML
before returning. If integrity validation fails, stop and use the printed
`git checkout HEAD -- <path>` recovery command before retrying from a clean
tree.
