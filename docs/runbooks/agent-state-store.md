# Agent State Store

## Purpose

This runbook covers ADR 0130: the repo-managed scratch state store that lets agents persist in-progress task state across workflow boundaries and verify that a recipient reads the same state after a handoff.

It is the repo-side reference for:

- provisioning `agent.state`
- writing and reading scratch state through `platform.agent.AgentStateClient`
- validating handoff integrity with a state digest
- inspecting or deleting state entries with the `lv3 agent state` CLI

## Canonical Sources

- ADR: [docs/adr/0130-agent-state-persistence-across-workflow-boundaries.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0130-agent-state-persistence-across-workflow-boundaries.md)
- schema migration: [migrations/0015_agent_state_schema.sql](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/migrations/0015_agent_state_schema.sql)
- Python client: [platform/agent/state.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/agent/state.py)
- CLI surface: [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py)
- client tests: [tests/test_agent_state_client.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/test_agent_state_client.py)

## Provision The Schema

Apply the migration on the control-plane Postgres instance:

```bash
psql "$LV3_AGENT_STATE_DSN" -f migrations/0015_agent_state_schema.sql
```

Verify the table and limits exist:

```bash
psql "$LV3_AGENT_STATE_DSN" -c "\d+ agent.state"
```

The schema-level guardrails are:

- `agent_id`, `task_id`, and `key` must be non-empty
- values larger than 64 KB are rejected
- more than 100 active keys in one `(agent_id, task_id)` namespace are rejected
- `expires_at` must remain after `written_at`

## Runtime Configuration

The client reads from:

- `LV3_AGENT_STATE_DSN`
- falls back to `WORLD_STATE_DSN` only when the dedicated variable is unset

Optional checkpoint publish path:

- `LV3_AGENT_STATE_NATS_URL`
- falls back to `LV3_NATS_URL`

Checkpoint events publish on `platform.agent.state_checkpoint` and include a `state_digest` that a downstream workflow can verify after reading the task state.

## Python Usage

```python
from platform.agent import AgentStateClient

state = AgentStateClient(
    agent_id="agent/runbook-executor",
    task_id="runbook-run:run-abc-123",
)

state.write("last_completed_step", "renew-cert")
checkpoint = state.checkpoint(
    {
        "step_results": {"renew-cert": {"status": "ok"}},
        "resume_at": "verify-health",
    }
)

verification = AgentStateClient(
    agent_id="agent/runbook-executor",
    task_id="runbook-run:run-abc-123",
).validate_handoff(checkpoint["state_digest"])

assert verification.matched is True
```

## CLI Inspection

Show the active state for one task:

```bash
lv3 agent state show --agent agent/triage-loop --task incident:inc-2026-03-24-001
```

Delete one key explicitly:

```bash
lv3 agent state delete --agent agent/triage-loop --task incident:inc-2026-03-24-001 --key hypothesis.1
```

Validate that a recipient sees the exact handoff snapshot:

```bash
lv3 agent state verify \
  --agent agent/runbook-executor \
  --task runbook-run:run-abc-123 \
  --digest 4d53d3f8d3b5fef6b6d52f3d2db06f0b57f81cb8e21f6b8f18a9730f88a20d70
```

Expected result:

```text
Integrity: ok
```

## Operational Notes

- Treat the store as scratch space only. Completed findings belong in the ledger or failure-case library, not here.
- A digest mismatch after handoff means the recipient is not reading the same active key set the sender checkpointed. Re-read the task state before taking action.
- Expired state is intentionally invisible to normal reads. Use `purge_expired()` in maintenance automation or a daily SQL job to remove old rows.
