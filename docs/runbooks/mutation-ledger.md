# Mutation Ledger

## Purpose

This runbook covers the ADR 0115 event-sourced mutation ledger: the Postgres schema, Python writer/reader/replay modules, the audit-log migration step, and the backward-compatible `audit_log` view.

It is the repo-side reference for:

- provisioning `ledger.events`
- validating the append-only contract
- migrating legacy ADR 0066 rows from `audit_log`
- enabling dual-write from existing mutation-audit emitters
- replaying recent service or VM state from the ledger

## Canonical Sources

- schema migration: [migrations/0011_ledger_schema.sql](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/migrations/0011_ledger_schema.sql)
- event type registry: [config/ledger-event-types.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/config/ledger-event-types.yaml)
- writer: [platform/ledger/writer.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/platform/ledger/writer.py)
- reader: [platform/ledger/reader.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/platform/ledger/reader.py)
- replay API: [platform/ledger/replay.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/platform/ledger/replay.py)
- migration helper: [windmill/ledger/migrate-audit-log.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/windmill/ledger/migrate-audit-log.py)
- legacy bridge: [scripts/mutation_audit.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server-mutation-ledger/scripts/mutation_audit.py)

## Schema Summary

`ledger.events` is append-only and stores:

- event identity: `id`, `event_id`, `event_type`, `occurred_at`
- actor context: `actor`, `actor_intent_id`, `tool_id`
- target context: `target_kind`, `target_id`
- state and evidence: `before_state`, `after_state`, `receipt`, `metadata`

The append-only guarantee is enforced in Postgres with a `BEFORE UPDATE OR DELETE` trigger that raises `ledger.events is append-only`.

## Provision The Schema

Apply the migration on the Postgres control-plane instance:

```bash
psql "$LV3_LEDGER_DSN" -f migrations/0011_ledger_schema.sql
```

Verify the table and trigger exist:

```bash
psql "$LV3_LEDGER_DSN" -c "\d+ ledger.events"
```

## Enable Dual-Write For Existing Emitters

When `LV3_LEDGER_DSN` is exported, the existing controller emitter writes the legacy JSONL/Loki audit event and then maps the same payload into `ledger.events`.

Optional fan-out after insert:

- `LV3_LEDGER_NATS_URL` or `LV3_NATS_URL`: publish `platform.ledger.event_written`

Example:

```bash
export LV3_LEDGER_DSN='postgresql://user:pass@postgres-lv3:5432/platform'
export LV3_LEDGER_NATS_URL='nats://docker-runtime-lv3:4222'
scripts/mutation_audit.py \
  --emit \
  --actor-class operator \
  --actor-id ops \
  --surface manual \
  --action document.manual_change \
  --target proxmox_florin \
  --outcome success
```

## Migrate Legacy `audit_log` Rows

Run the one-time helper after the schema exists:

```bash
python windmill/ledger/migrate-audit-log.py --dsn "$LV3_LEDGER_DSN"
```

Default behavior:

- reads `audit_log` in ascending `id` order
- inserts legacy rows into `ledger.events` with `before_state` and `after_state` set to `null`
- marks migrated rows with `metadata.legacy_event: true` and `metadata.state_capture: false`
- renames the old table to `audit_log_legacy`
- creates `audit_log` as a compatibility view over `ledger.events`

First production rollout note:

- if `public.audit_log` does not exist yet, the helper now skips row migration and still installs the compatibility `audit_log` view
- the 2026-03-26 production apply hit that path because ADR 0066 was still writing JSONL/Loki only, so the SQL migration moved `0` rows

Current live credential note:

- the current production controller-local superuser password is for the `patroni` role, so the live ledger DSN targets `postgresql://patroni@.../postgres`, not `postgresql://postgres@...`

If you need a dry staging pass that leaves the old table name untouched:

```bash
python windmill/ledger/migrate-audit-log.py \
  --dsn "$LV3_LEDGER_DSN" \
  --preserve-legacy-table
```

## Verify Append-Only Enforcement

This statement must fail:

```bash
psql "$LV3_LEDGER_DSN" -c "UPDATE ledger.events SET event_type = 'tampered' WHERE id = 1"
```

Expected error text:

```text
ledger.events is append-only
```

## Replay Recent State

Example Python snippet:

```python
from platform.ledger import LedgerReplayer

replayer = LedgerReplayer(dsn="postgresql://user:pass@postgres-lv3:5432/platform")

events = replayer.slice(
    target_kind="service",
    target_id="netbox",
    from_ts="2026-03-24T00:00:00Z",
    to_ts="2026-03-24T12:00:00Z",
)

state_at = replayer.project_state("service:netbox", at="2026-03-24T06:00:00Z")
```

Current projection support is intentionally narrow:

- `service:<id>`
- `vm:<id>`

Other target kinds raise `NotImplementedError` until their projection logic is defined.

## Windmill Runtime Projection

When projecting the ledger DSN into the Windmill runtime, keep both templates in sync:

- [roles/windmill_runtime/templates/windmill.env.j2](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0115-live-apply/roles/windmill_runtime/templates/windmill.env.j2)
- [roles/windmill_runtime/templates/windmill.env.ctmpl.j2](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0115-live-apply/roles/windmill_runtime/templates/windmill.env.ctmpl.j2)

If only the OpenBao-backed template is updated, the later static `windmill.env.j2` render will still overwrite `/run/lv3-secrets/windmill/runtime.env` without the ledger keys.

During the 2026-03-26 production apply, concurrent Windmill converges from other worktrees repeatedly rewrote the same env surfaces. When this happens:

- update the OpenBao secret `services/windmill/runtime-env`
- update the rendered `/run/lv3-secrets/windmill/runtime.env` with the same ledger values if another converge already flattened the file
- recycle the Windmill compose services
- if the restart fails because the Docker `DOCKER` nat chain is missing, restart `docker` first and then rerun `docker compose --file /opt/windmill/docker-compose.yml up -d --remove-orphans`
