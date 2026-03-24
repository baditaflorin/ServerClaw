# ADR 0156: Agent Session Workspace Isolation

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Multiple agents running concurrently on the same platform share several mutable namespaces:

**The agent state store** (ADR 0130) partitions by `(agent_id, task_id)`, which prevents one agent from overwriting another's state. However, agents reading each other's intermediate state is possible: a triage agent can query the state store for a task owned by a runbook executor agent, potentially reading partial or inconsistent state from an in-progress multi-step task.

**The Postgres scratch space**: Several platform workflows create temporary tables, use `pg_temp` schemas, or write to shared tables during execution (e.g., the diff engine ADR 0120 writes dry-run results to `platform.diff_results`). Two concurrent dry-run executions targeting different services both write to `platform.diff_results` using `service_id` as a partition key — which is correct for reads, but a TRUNCATE on the table by one workflow clears the other's results.

**The file system on `docker-build-lv3`**: Build workflows write to working directories on the build VM. The convention is `$BUILD_DIR/{workflow_run_id}` but this is not enforced. A build workflow that uses a hardcoded `/tmp/build` path will corrupt a concurrent build.

**The NATS subject namespace**: Agents publish to canonical subjects like `platform.agent.context.{agent_id}`. Two concurrent sessions of the same agent type (e.g., two Claude Code sessions) share the same `agent_id` and will mix their published state.

**The live-apply receipt file**: The platform commits receipts to `receipts/{date}-{workflow_id}.json`. If two concurrent workflows have the same `workflow_id` root (e.g., both are `converge-netbox`), the receipt filename collision causes one receipt to overwrite the other.

These are correctness bugs under concurrent agent load, not just performance issues. Each is individually fixable, but the correct fix is a **uniform workspace isolation model** that gives every concurrent agent session its own namespace for every mutable surface.

## Decision

We will implement **agent session workspace isolation**: every concurrent session gets an ephemeral, automatically-provisioned and automatically-cleaned-up isolated namespace for each mutable surface it uses.

### Session workspace model

A workspace is created by the session bootstrap (ADR 0123) and destroyed when the session ends:

```python
# platform/workspace/session.py

@dataclass
class SessionWorkspace:
    context_id: UUID        # From SessionContext (ADR 0123)
    session_id: str         # Unique session identifier: "{agent_id}:{context_id_short}"

    # Workspace roots (all unique per session)
    postgres_schema: str    # e.g., "ws_a1b2c3"
    build_dir: Path         # e.g., "/data/builds/a1b2c3"
    nats_prefix: str        # e.g., "platform.ws.a1b2c3"
    receipt_prefix: str     # e.g., "receipts/2026-03-24/a1b2c3"
    state_namespace: str    # e.g., "ws:a1b2c3" (appended to task_id in state store)
```

### 1. Ephemeral Postgres schema

Each session creates an isolated Postgres schema for all temporary/scratch data:

```python
# On session start (bootstrap, ADR 0123)
def create_workspace_schema(ctx: SessionContext) -> str:
    schema_name = f"ws_{ctx.context_id.hex[:8]}"
    db.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    # Grant usage to the platform service account
    db.execute(f"GRANT ALL ON SCHEMA {schema_name} TO platform_service")
    return schema_name
```

All session-local scratch tables are created in this schema:

```python
# In the diff engine (ADR 0120) — uses workspace schema instead of public platform schema
db.execute(f"""
    CREATE TABLE {workspace.postgres_schema}.diff_results (
        service_id TEXT, diff_summary JSONB, created_at TIMESTAMPTZ DEFAULT now()
    )
""")
```

On session end (success, failure, or TTL expiry), the schema is dropped:

```python
# On session cleanup (called by Windmill job finaliser)
def destroy_workspace_schema(workspace: SessionWorkspace):
    db.execute(f"DROP SCHEMA IF EXISTS {workspace.postgres_schema} CASCADE")
```

Schema cleanup is also enforced by a nightly Windmill workflow `cleanup-abandoned-workspaces` that drops any `ws_*` schemas older than 2 hours with no active context_id in the session registry.

### 2. Isolated build directory

Build workflows receive the session build directory, not a hardcoded path:

```python
# In Windmill build script
workspace = get_session_workspace()  # Injected by Windmill job context
build_dir = workspace.build_dir      # /data/builds/{context_id_short}
build_dir.mkdir(parents=True, exist_ok=True)

# Ansible Packer run uses workspace-scoped temp files
run_packer(work_dir=build_dir / "packer", output_dir=build_dir / "artifacts")
```

The `docker-build-lv3` VM mounts `/data/builds` as a Docker volume with per-session subdirectories. On session end, the build directory is deleted unless the session produced an artifact that is being kept (e.g., a container image that was pushed, or a receipt that was committed).

### 3. Scoped NATS subjects

Agents publishing ephemeral state (in-progress diagnostics, partial triage reports, intermediate goal compiler state) publish to the session-scoped NATS prefix rather than the canonical agent prefix:

```python
# Instead of:
nats.publish("platform.agent.state.agent/triage-loop", partial_state)

# Use:
nats.publish(f"{workspace.nats_prefix}.state", partial_state)
# → "platform.ws.a1b2c3.state"
```

The canonical agent subjects (`platform.agent.state.{agent_id}`) remain for **committed** state that should be visible to all agents. The workspace-scoped subjects are for ephemeral in-progress data that should not be visible to other sessions.

The real-time agent coordination map (ADR 0161) aggregates workspace-scoped subjects into a per-session view for operators, without exposing partial state from one session to other sessions.

### 4. Collision-safe receipt filenames

Receipt files are written to a workspace-scoped path:

```python
# receipts/{YYYY-MM-DD}/{workflow_id}_{context_id_short}.receipt.json
receipt_path = f"receipts/{today}/{intent.workflow_id}_{workspace.context_id_short}.receipt.json"
```

This eliminates the filename collision problem: two concurrent `converge-netbox` runs produce `converge-netbox_a1b2c3.receipt.json` and `converge-netbox_d4e5f6.receipt.json` respectively.

### 5. State store namespace scoping

The agent state store (ADR 0130) partitions by `(agent_id, task_id)`. Under concurrent sessions, the same agent running multiple tasks concurrently could mix state entries. Workspace isolation adds the `context_id` as a third partition dimension:

```sql
-- Updated primary key for agent.state table
ALTER TABLE agent.state ADD COLUMN context_id UUID;
ALTER TABLE agent.state DROP CONSTRAINT agent_state_pkey;
ALTER TABLE agent.state ADD PRIMARY KEY (agent_id, task_id, key, context_id);
```

Old state entries (from before this ADR) have `context_id = NULL` and continue to work. New entries always include `context_id`.

### Workspace registry

Active workspaces are tracked in a Postgres table for cleanup and monitoring:

```sql
CREATE TABLE platform.session_workspaces (
    context_id      UUID PRIMARY KEY,
    agent_id        TEXT NOT NULL,
    postgres_schema TEXT NOT NULL,
    build_dir       TEXT,
    nats_prefix     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'  -- active | completed | expired | cleaning
);
```

The real-time coordination map (ADR 0161) reads this table to show which workspaces are active.

## Consequences

**Positive**

- Concurrent sessions are fully isolated from each other's intermediate state. A triage agent running two concurrent diagnoses of different services cannot mix their scratch data.
- The receipt filename collision problem is eliminated by design.
- Workspace cleanup is automatic and systematic; abandoned workspaces (from crashed sessions) are removed by the nightly cleanup job.

**Negative / Trade-offs**

- The ephemeral Postgres schema model requires that all scratch SQL uses the workspace schema name rather than a hardcoded schema. Every existing workflow that writes to `platform.*` scratch tables must be audited and updated.
- The build directory scoping requires every build script to use `workspace.build_dir` rather than a hardcoded path. This is a convention that must be enforced by code review or a linter.
- Workspace schemas accumulate in Postgres between the session end and the next nightly cleanup run. In a high-frequency session environment, this could create dozens of schemas. The `pg_schemas` catalog has no hard limit, but schema proliferation should be monitored.

## Boundaries

- Workspace isolation covers scratch and ephemeral data. Committed data (mutation ledger entries, final receipts, search index documents) always goes to the canonical shared tables and is not workspace-scoped.
- The state store workspace scoping (new `context_id` column) is backward-compatible. Existing agents that do not set `context_id` continue to use the `NULL` partition.

## Related ADRs

- ADR 0036: Live-apply receipts (collision-safe filename from this ADR)
- ADR 0115: Event-sourced mutation ledger (canonical committed data; not workspace-scoped)
- ADR 0120: Dry-run semantic diff engine (diff_results table moved to workspace schema)
- ADR 0123: Agent session bootstrap (workspace created/destroyed alongside session context)
- ADR 0130: Agent state persistence (context_id added as partition dimension)
- ADR 0154: VM-scoped execution lanes (lane scheduler references workspace for lock acquisition)
- ADR 0161: Real-time agent coordination map (reads workspace registry for per-session view)
