# Health Composite Index

## Purpose

ADR 0128 defines the repository-managed composite health index used by the platform API, CLI, and goal compiler.

## Query The Current Index

- local CLI summary: `lv3 health`
- one service with signal detail: `lv3 health netbox --verbose`
- API aggregate: `GET /v1/platform/health`
- API per-service: `GET /v1/platform/health/netbox`

## Refresh Path

The durable refresh path is the Windmill worker:

- script: `f/lv3/health/refresh_composite`
- schedule seed: `f/lv3/health/refresh_composite_every_minute`

Repository code for that worker lives at `config/windmill/scripts/health/refresh-composite.py`.

## Troubleshooting

If the index looks stale or incomplete:

1. Confirm world-state service health is available.
2. Check the latest drift receipt under `receipts/drift-reports/`.
3. Check active triage reports under `.local/triage/reports/`.
4. Check the ledger state under `.local/state/ledger/ledger.events.jsonl` or the live `ledger.events` table.
5. If the Postgres-backed table is missing, apply `migrations/0013_health_schema.sql` from `main` before enabling the Windmill schedule.
