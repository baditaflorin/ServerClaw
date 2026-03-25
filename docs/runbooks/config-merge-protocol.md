# Config Merge Protocol

## Purpose

ADR 0158 adds a conflict-free merge path for append-heavy registry files. Instead of writing directly to the repo file, automation stages one change row in `config_change_staging` and the merge worker applies pending rows into the merge-eligible files catalog.

## Canonical Sources

- merge-eligible file catalog: [config/merge-eligible-files.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/merge-eligible-files.yaml)
- runtime module: [platform/config_merge](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/config_merge)
- operator CLI: [scripts/config_merge_protocol.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/config_merge_protocol.py)
- Windmill worker wrapper: [config/windmill/scripts/merge-config-changes.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/merge-config-changes.py)
- schema migration: [migrations/0016_config_merge_schema.sql](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0016_config_merge_schema.sql)

## Merge-Eligible Files

The first live set is:

- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/workflow-catalog.json`
- `config/agent-policies.yaml`

Each file declares:

- the collection path inside the file
- whether the collection is a list or mapping
- the unique key field
- whether duplicate keys are rejected or resolved by last-write-wins

Files outside this catalog still use the normal exclusive git edit path.

## Stage A Change

Stage one append into a merge-eligible file:

```bash
python3 scripts/config_merge_protocol.py stage-append \
  --file config/service-capability-catalog.json \
  --entry '{"id":"netbox","name":"NetBox","description":"Source of truth"}' \
  --actor agent/codex \
  --context-id 00000000-0000-0000-0000-000000000158 \
  --dsn "$LV3_CONFIG_MERGE_DSN"
```

For mapping-backed files such as `config/workflow-catalog.json`, the entry payload may include the key field directly:

```bash
python3 scripts/config_merge_protocol.py stage-append \
  --file config/workflow-catalog.json \
  --entry '{"workflow_id":"merge-config-changes","description":"Merge staged rows"}' \
  --actor operator:lv3_cli \
  --context-id 00000000-0000-0000-0000-000000000159 \
  --dsn "$LV3_CONFIG_MERGE_DSN"
```

## Preview The Overlay

Render the file with pending rows overlaid, without touching the tracked file on disk:

```bash
python3 scripts/config_merge_protocol.py read \
  --file config/service-capability-catalog.json \
  --dsn "$LV3_CONFIG_MERGE_DSN"
```

## Merge Pending Rows

Run the merge worker directly from a controller checkout:

```bash
make merge-config-changes
```

Equivalent low-level command:

```bash
python3 scripts/config_merge_protocol.py merge --dsn "$LV3_CONFIG_MERGE_DSN"
```

The Windmill runtime seeds the same worker as:

- script path: `f/lv3/config_merge/merge_config_changes`
- schedule path: `f/lv3/config_merge/merge_config_changes_every_minute`

## Live Apply

The live path is part of the Windmill converge:

1. `make preflight WORKFLOW=converge-windmill`
2. `make converge-windmill`

That converge now:

- applies `migrations/0016_config_merge_schema.sql` to the Windmill PostgreSQL database
- seeds the `f/lv3/config_merge/merge_config_changes` script
- enables the minute schedule `f/lv3/config_merge/merge_config_changes_every_minute`

## Verification

Validate the repo-side contract:

```bash
python3 scripts/config_merge_protocol.py validate
uv run --with pytest --with pyyaml pytest -q \
  tests/test_config_merge_protocol.py \
  tests/test_config_merge_repo_surfaces.py \
  tests/test_config_merge_windmill.py \
  tests/unit/test_event_taxonomy.py
```

Verify the live database and Windmill seeds after `make converge-windmill`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.50 \
  "psql -d windmill -Atqc \"SELECT to_regclass('public.config_change_staging')\""

curl -s \
  -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  http://100.118.189.95:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fconfig_merge%2Fmerge_config_changes
```

Expected results:

- the Postgres query returns `public.config_change_staging`
- the Windmill job returns a JSON payload with `status: ok`

## Conflict Handling

If a row cannot be applied:

- its `status` becomes `conflict`
- the worker emits `platform.config.merge_conflict`
- the pending rows for other keys in the same file still merge on the same run

Use the staging table to inspect the blocked row:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.50 \
  "psql -d windmill -x -c \"SELECT change_id, file_path, key_value, status, status_reason FROM config_change_staging WHERE status = 'conflict' ORDER BY submitted_at DESC\""
```
