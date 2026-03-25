# Workflow Idempotency

## Purpose

ADR 0165 adds deterministic workflow idempotency keys so the scheduler can suppress duplicate submissions, return cached results for completed retries, and expose those hits to operators.

## Canonical Sources

- key construction: [platform/idempotency/keys.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/idempotency/keys.py)
- store implementation: [platform/idempotency/store.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/idempotency/store.py)
- scheduler integration: [platform/scheduler/scheduler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py)
- Postgres schema: [migrations/0016_idempotency_store.sql](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0016_idempotency_store.sql)

## Operator Paths

Show one compiled intent status:

```bash
lv3 intent status <intent_id>
```

Inspect the shared file-backed fallback state:

```bash
cat "$(git rev-parse --git-common-dir)/lv3-idempotency/records.json"
```

Apply the live Postgres schema when the runtime DSN is available:

```bash
psql "${LV3_IDEMPOTENCY_DSN:-$LV3_LEDGER_DSN}" -f migrations/0016_idempotency_store.sql
```

## Runtime Model

- when `LV3_IDEMPOTENCY_DSN` is set, the scheduler uses the Postgres-backed `platform.idempotency_records` table
- when that variable is unset, the scheduler falls back to a shared git-common-dir JSON state file so multiple local worktrees still deduplicate against each other
- completed submissions are returned as `idempotent_hit`
- active duplicates return `in_flight` with the original Windmill job handle when available
- failed, aborted, budget-exceeded, and rolled-back records are retryable on the next submission

## Verification

Confirm the schema exists live:

```bash
psql "${LV3_IDEMPOTENCY_DSN:-$LV3_LEDGER_DSN}" -c "\d+ platform.idempotency_records"
```

Confirm expired records are removable:

```bash
psql "${LV3_IDEMPOTENCY_DSN:-$LV3_LEDGER_DSN}" -c "DELETE FROM platform.idempotency_records WHERE expires_at < now();"
```

Confirm an idempotent hit from the operator path:

```bash
lv3 intent status <intent_id>
```

The output should show `Status: idempotent_hit` and the original execution reference when the cached path was used.
