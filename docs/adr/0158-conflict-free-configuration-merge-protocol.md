# ADR 0158: Conflict-Free Configuration Merge Protocol

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Several platform configuration files are **append-heavy registries**: multiple agents or operators add entries to them, but entries are rarely modified or deleted. Examples:

- `config/service-capability-catalog.json` — agents add new service entries.
- `config/subdomain-catalog.json` — agents register new subdomains.
- `config/workflow-catalog.yaml` — agents publish new workflow templates.
- `config/agent-policies.yaml` — operators grant capabilities to new agent identities.
- `config/oauth2-clients.yaml` — agents register new OIDC clients.
- `config/nats-subjects.yaml` — agents declare new event subjects.

Today, modifications to these files go through the standard git commit/merge pipeline with exclusive lock semantics: one agent writes, commits, and the next agent reads the updated file. This is correct but slow under parallel load.

The problem becomes acute with multiple agents working on parallel goals. Three agents simultaneously deploying new services each need to register their service in `config/service-capability-catalog.json`. With exclusive git commits:
- Agent A acquires the write lock, reads the file, appends its entry, commits.
- Agent B must wait for A to commit before reading and appending.
- Agent C must wait for B.

Total time: 3 × commit_time (plus merge conflict resolution if any agent branched).

This serialises what is logically parallel work: the three service entries are independent. Agent A's new entry does not affect Agent B's new entry. The serialisation is an artefact of treating the file as a single opaque unit rather than as a collection of independent entries.

The solution is to treat these append-heavy registries as **sets of independent records** with merge semantics, rather than as files with last-write-wins semantics.

## Decision

We will implement a **conflict-free configuration merge protocol** for all append-heavy registry files. Rather than serialised file writes, agents write to a Postgres-backed **change staging table** and a merge job combines staged changes into the registry file on a defined schedule.

### Merge-eligible file classification

The validation pipeline (ADR 0031) maintains a list of files classified as merge-eligible:

```yaml
# config/merge-eligible-files.yaml

merge_eligible:
  - file: config/service-capability-catalog.json
    merge_strategy: set_by_key
    key_field: service_id
    conflict_resolution: reject_duplicate_key  # Two entries with same service_id → error

  - file: config/subdomain-catalog.json
    merge_strategy: set_by_key
    key_field: subdomain
    conflict_resolution: reject_duplicate_key

  - file: config/workflow-catalog.yaml
    merge_strategy: set_by_key
    key_field: workflow_id
    conflict_resolution: reject_duplicate_key

  - file: config/agent-policies.yaml
    merge_strategy: set_by_key
    key_field: agent_id
    conflict_resolution: last_write_wins    # Agent policy updates are idempotent

  - file: config/oauth2-clients.yaml
    merge_strategy: set_by_key
    key_field: client_id
    conflict_resolution: reject_duplicate_key
```

Files **not** listed here use the standard exclusive lock + commit model. Modification of non-merge-eligible files (e.g., `versions/stack.yaml`) still requires an exclusive write lock.

### Staging table

```sql
-- platform/migrations/0158_config_merge_staging.sql
CREATE TABLE platform.config_change_staging (
    change_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path       TEXT NOT NULL,          -- e.g., "config/service-capability-catalog.json"
    operation       TEXT NOT NULL,          -- 'append' | 'update' | 'delete'
    key_value       TEXT NOT NULL,          -- Value of the key_field (e.g., service_id)
    entry_json      JSONB NOT NULL,         -- The complete entry to add/update
    submitted_by    TEXT NOT NULL,          -- Agent identity
    context_id      UUID NOT NULL,
    submitted_at    TIMESTAMPTZ DEFAULT now(),
    merged_at       TIMESTAMPTZ,
    status          TEXT DEFAULT 'pending'  -- pending | merged | conflict | rejected
);
```

### Agent write API

Instead of writing directly to the config file, agents submit to the staging table:

```python
# platform/config/registry.py

class ConfigRegistry:

    def append_entry(
        self,
        file_path: str,
        entry: dict,
        actor: str,
        context_id: UUID,
    ) -> ChangeStagingHandle:
        """
        Stage a new entry for merge into a merge-eligible config file.
        Returns immediately; does not wait for the merge job to run.
        """
        key_field = self._get_key_field(file_path)
        key_value = entry[key_field]

        # Optimistic duplicate check: reject immediately if key already exists
        existing = self._read_current_entry(file_path, key_value)
        if existing and self._get_conflict_resolution(file_path) == "reject_duplicate_key":
            raise DuplicateKeyError(f"{key_field}={key_value} already exists in {file_path}")

        change_id = db.insert("platform.config_change_staging", {
            "file_path": file_path,
            "operation": "append",
            "key_value": key_value,
            "entry_json": entry,
            "submitted_by": actor,
            "context_id": context_id,
        })
        return ChangeStagingHandle(change_id=change_id)
```

### Merge job

A Windmill workflow `merge-config-changes` runs every 60 seconds and on-demand (triggered by a NATS event when any staging entry is submitted):

```python
def merge_config_changes():
    pending = db.query("""
        SELECT * FROM platform.config_change_staging
        WHERE status = 'pending'
        ORDER BY submitted_at ASC
        FOR UPDATE SKIP LOCKED
    """)

    # Group by file_path
    by_file = group_by(pending, key=lambda r: r.file_path)

    for file_path, changes in by_file.items():
        strategy = load_merge_strategy(file_path)
        current_content = read_file(file_path)

        # Apply all pending changes for this file in one commit
        merged_content, conflicts = apply_changes(current_content, changes, strategy)

        if conflicts:
            # Mark conflicting changes and notify actors
            for conflict in conflicts:
                db.execute(
                    "UPDATE platform.config_change_staging SET status='conflict' WHERE change_id=:id",
                    id=conflict.change_id
                )
                nats.publish(f"platform.config.merge_conflict.{conflict.change_id}", conflict.__dict__)
        else:
            # Write merged content and commit
            write_file(file_path, merged_content)
            git_commit_and_push(
                files=[file_path],
                message=f"config: merge {len(changes)} staged changes to {file_path}",
                actor="agent/config-merge-job",
            )
            for change in changes:
                db.execute(
                    "UPDATE platform.config_change_staging SET status='merged', merged_at=now() WHERE change_id=:id",
                    id=change.change_id
                )
                nats.publish(f"platform.config.merged.{change.change_id}", {"status": "merged"})
```

### Conflict resolution for `set_by_key` strategy

The merge algorithm for `set_by_key` files:

1. Parse the current file as a list of objects.
2. For each staged `append` operation: check if `key_value` already exists in the list. If yes and `conflict_resolution: reject_duplicate_key`, mark as conflict. If no, append.
3. For each staged `update` operation: find the existing entry by key, replace it.
4. For each staged `delete` operation: remove the entry by key.
5. Write the merged list back.

Since entries are identified by a unique key field, two concurrent `append` operations with different keys are always mergeable with zero conflict.

### Agents reading staged (not-yet-merged) entries

An agent that submits a new service entry and immediately queries the capability catalog may not see its own entry (the merge job runs every 60 seconds). The `ConfigRegistry.read` API accounts for this by overlaying pending staged entries on top of the current file content:

```python
def read_all(self, file_path: str, include_pending: bool = True) -> list[dict]:
    current = parse_file(file_path)
    if include_pending:
        staged = db.query(
            "SELECT entry_json FROM platform.config_change_staging WHERE file_path=:f AND status='pending'",
            f=file_path
        )
        # Overlay staged entries on current (staged takes priority for same key)
        merged = merge_by_key(current, [s.entry_json for s in staged], key_field=self._get_key_field(file_path))
        return merged
    return current
```

## Consequences

**Positive**

- Three agents simultaneously registering new services can all submit their entries without blocking each other. The 60-second merge job consolidates all three in a single commit. Total time: 60 seconds instead of 3 × commit_time (typically 3 × 30 seconds = 90 seconds, plus merge conflict overhead).
- Agents that need to read their own just-submitted entries immediately get a consistent view via the overlay read.
- The merge job creates structured git commits that are easy to audit: "config: merge 3 staged changes to service-capability-catalog.json" is more informative than three sequential commits from three agents.

**Negative / Trade-offs**

- The merge job is a single-point centralised writer for each config file. If the merge job fails, pending staged changes accumulate and are applied on the next run. Agents must handle the case where their staged entry is not reflected in the file for up to 60 seconds + one merge job run.
- The staging table is a new persistent data store that must be backed up. Staged changes that are lost (due to Postgres failure between submission and merge) cannot be recovered. The 60-second window is small, but for critical config changes, agents should poll the staging status before proceeding.

## Boundaries

- Only files listed in `config/merge-eligible-files.yaml` use this protocol. All other config files continue to use the exclusive lock + commit model.
- The merge protocol does not handle structural changes to config files (adding a new required field to all entries, reordering sections). Those are breaking changes requiring a migration playbook.

## Related ADRs

- ADR 0031: Repository validation pipeline (merge-eligible file list; commit validation)
- ADR 0075: Service capability catalog (primary merge-eligible file)
- ADR 0076: Subdomain governance (merge-eligible)
- ADR 0115: Event-sourced mutation ledger (config.merge_conflict and config.merged events)
- ADR 0124: Platform event taxonomy (platform.config.merged.* events trigger downstream reindexing)
- ADR 0153: Distributed resource lock registry (non-merge-eligible files still use lock)
- ADR 0155: Intent queue (merge_conflict event triggers agent notification)
