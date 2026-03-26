# Workstream ADR 0158: Conflict-Free Configuration Merge Protocol

- ADR: [ADR 0158](../adr/0158-conflict-free-configuration-merge-protocol.md)
- Title: queue append-heavy registry changes into `config_change_staging` and merge them through one governed Windmill writer
- Status: merged
- Implemented In Repo Version: 0.154.0
- Live Applied In Platform Version: not yet
- Implemented On: 2026-03-25
- Live Applied On: not yet
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
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.50 "psql -d windmill -Atqc \"SELECT to_regclass('public.config_change_staging')\""`
- `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fconfig_merge%2Fmerge_config_changes`

## Merge Criteria

- merge-eligible file definitions validate through the shared repo data-model gate
- list-backed and mapping-backed registries both merge correctly from staged rows
- the Windmill runtime converge applies the migration and seeds the config-merge worker
- the live Windmill worker returns a successful run result from the production control plane

## Outcome

- repository implementation is complete on `main` in repo release `0.154.0`
- the repo now ships the merge-eligible catalog, staging-table migration, `platform.config_merge`, the operator CLI, the Windmill merge worker, canonical config-merge events, and focused repo plus Windmill tests
- live apply is still pending because `make converge-windmill` failed immediately on `proxmox_florin` with `ssh: connect to host 100.64.0.1 port 22: Connection refused`, the public fallback `ops@65.108.75.123:22` timed out, and the private Proxmox API probe `https://100.64.0.1:8006` also failed during the same window
