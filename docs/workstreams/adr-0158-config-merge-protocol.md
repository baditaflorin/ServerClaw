# Workstream ADR 0158: Conflict-Free Configuration Merge Protocol

- ADR: [ADR 0158](../adr/0158-conflict-free-configuration-merge-protocol.md)
- Title: queue append-heavy registry changes into `config_change_staging` and merge them through one governed Windmill writer
- Status: live_applied
- Implemented In Repo Version: 0.154.0
- Live Applied In Platform Version: 0.130.17
- Implemented On: 2026-03-25
- Live Applied On: 2026-03-26
- Branch: `codex/adr-0158-config-merge-protocol`
- Worktree: `.worktrees/adr-0158-config-merge`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0087-validation-gate`, `adr-0115-mutation-ledger`, `adr-0124-platform-event-taxonomy`
- Conflicts With: none
- Shared Surfaces: `platform/config_merge/`, `scripts/config_merge_protocol.py`, `config/merge-eligible-files.yaml`, `config/event-taxonomy.yaml`, `config/control-plane-lanes.json`, `config/api-publication.json`, `config/workflow-catalog.json`, `config/command-catalog.json`, `migrations/0016_config_merge_schema.sql`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `docs/runbooks/config-merge-protocol.md`

## Scope

- add ADR 0158 plus the matching workstream and runbook documentation
- add `config/merge-eligible-files.yaml` as the canonical registry of merge-eligible files and merge semantics
- implement `platform/config_merge` and `scripts/config_merge_protocol.py` for staging, overlay reads, and merge application
- add the Windmill wrapper and seed it through the managed Windmill runtime
- apply the new staging-table migration during `make converge-windmill`
- publish canonical config-merge events and register the new worker in the workflow, command, lane, and publication catalogs
- add focused tests for merge semantics, repo surfaces, and the Windmill wrapper

## Non-Goals

- replacing normal git workflows for non-merge-eligible files
- building a generic structural migration engine for every config file shape in the first iteration
- allowing unmanaged callers to bypass the governed merge catalog and write directly into the staging table

## Expected Repo Surfaces

- `platform/config_merge/`
- `scripts/config_merge_protocol.py`
- `config/merge-eligible-files.yaml`
- `config/windmill/scripts/merge-config-changes.py`
- `migrations/0016_config_merge_schema.sql`
- `config/event-taxonomy.yaml`
- `config/control-plane-lanes.json`
- `config/api-publication.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/main.yml`
- `docs/runbooks/config-merge-protocol.md`
- `tests/test_config_merge_protocol.py`
- `tests/test_config_merge_repo_surfaces.py`
- `tests/test_config_merge_windmill.py`
- `tests/unit/test_event_taxonomy.py`

## Expected Live Surfaces

- `public.config_change_staging` exists in the Windmill PostgreSQL database
- Windmill exposes `f/lv3/config_merge/merge_config_changes`
- Windmill enables `f/lv3/config_merge/merge_config_changes_every_minute`
- the merge worker can read pending rows and return `status: ok` when invoked manually
- merged and conflict outcomes publish on the internal `platform.config.*` subjects

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_config_merge_protocol.py tests/test_config_merge_repo_surfaces.py tests/test_config_merge_windmill.py tests/unit/test_event_taxonomy.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make syntax-check-windmill`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.50 "psql -d windmill -Atqc \"SELECT to_regclass('public.config_change_staging')\""`
- `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/get/f%2Flv3%2Fconfig_merge%2Fmerge_config_changes_every_minute`

## Merge Criteria

- merge-eligible file definitions validate through the shared repo data-model gate
- list-backed and mapping-backed registries both merge correctly from staged rows
- the Windmill runtime converge applies the migration and seeds the config-merge worker
- the live Windmill worker returns a successful run result from the production control plane when invoked with the managed database DSN, and the scheduled path keeps that DSN in the repo-managed Windmill schedule arguments

## Outcome

- the repository implementation first landed on `main` in repo release `0.154.0`, and the integrated live apply from current `main` is recorded in release `0.167.0`
- the 2026-03-26 live verification advanced platform version to `0.130.17` after `make converge-windmill` passed, `public.config_change_staging` remained present in the Windmill PostgreSQL database, the managed schedule kept the production DSN in `args.dsn`, and the live worker returned `status: ok` with `pending_count: 0` against the production control plane
- ad hoc empty-body manual runs remain blocked outside the governed schedule context because Windmill does not reliably expose `DATABASE_URL` into the job sandbox; the live production path is the managed minute schedule that now carries the repo-managed DSN explicitly
