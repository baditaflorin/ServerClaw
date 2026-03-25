# ADR 0158: Conflict-Free Configuration Merge Protocol

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.154.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

Several LV3 config files are append-heavy registries:

- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/workflow-catalog.json`
- `config/agent-policies.yaml`

These files describe independent records, but parallel agents still collide because the repo normally treats each file as one locked write surface. Under load, unrelated appends serialize behind each other and branch merges degrade into avoidable file-level conflicts.

## Decision

We treat selected registry files as merge-eligible collections and stage changes in a database-backed queue before a single merge worker materializes them into the tracked files.

### Canonical merge catalog

`config/merge-eligible-files.yaml` is the source of truth for:

- which files are merge-eligible
- where the mergeable collection lives inside each file
- whether the collection is a list or a mapping
- the key field for uniqueness
- whether duplicates are rejected or resolved by last-write-wins

### Staging model

Pending writes land in `config_change_staging` with:

- file path
- operation
- key value
- full entry payload
- actor and context id
- submitted, merged, and status fields

### Merge writer

`platform.config_merge.ConfigMergeRegistry` now owns:

- staging one append operation
- overlay reads that include pending rows
- file merges for list-backed and mapping-backed registries
- conflict marking for duplicate or invalid operations
- optional `platform.config.merged` and `platform.config.merge_conflict` event publication

### Live runtime

The Windmill converge now applies `migrations/0016_config_merge_schema.sql`, seeds `f/lv3/config_merge/merge_config_changes`, and enables the minute schedule `f/lv3/config_merge/merge_config_changes_every_minute`.

## Implementation Notes

- The repo runtime lives under `platform/config_merge/` and the operator CLI entry point is `scripts/config_merge_protocol.py`.
- `config/command-catalog.json`, `config/workflow-catalog.json`, `config/control-plane-lanes.json`, and `config/api-publication.json` now register the merge worker as a governed live surface.
- `config/event-taxonomy.yaml` now declares the canonical config-merge subjects.
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/` now applies the staging-table migration and seeds the worker plus schedule during `make converge-windmill`.

## Consequences

### Positive

- Independent appends no longer need exclusive file ownership.
- Agents can read their own staged entries immediately through overlay reads.
- Conflicts become row-level state in `config_change_staging` instead of opaque git merge failures.
- Windmill owns one durable merge writer instead of ad hoc registry mutations from many callers.

### Trade-Offs

- The staging table is now part of the live control-plane state and must stay backed up with the Windmill database.
- Merge conflicts shift from git to the staging queue; operators still need a runbook for clearing them.
- Merge-eligible files are a bounded opt-in set. Non-listed files still require the normal exclusive git path.

## Related ADRs

- ADR 0031: Repository validation pipeline for automation changes
- ADR 0044: Windmill for agent and operator workflows
- ADR 0075: Service capability catalog
- ADR 0076: Subdomain governance and DNS lifecycle
- ADR 0115: Event-sourced mutation ledger
- ADR 0124: Platform event taxonomy and canonical NATS topics
