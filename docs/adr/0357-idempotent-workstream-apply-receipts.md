# ADR 0357: Idempotent Workstream Apply Receipts

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Scoping Note (2026-04-06): Pure state machine — YAML receipt file with in_progress/completed/failed/partial states + guard clauses in apply logic. Add to existing workstream system. Priority 5 in implementation order.
- Tags: workstreams, audit, idempotency, agent-coordination, receipts, infrastructure

## Context

The platform uses workstreams (e.g., `ws-0346`) to track units of work
delivered by agents. Each workstream has a lifecycle: `active → live-applied
→ main-merged → archived`. The `receipts/live-applies/` directory stores JSON
receipts that record when a workstream's changes were applied to the live
environment.

However, there is no mechanism to prevent an agent from applying the same
workstream twice to the same environment. Duplicate applies can cause:
- Double service restarts.
- Secret rotation applied twice (potential downtime).
- Duplicate entries in the changelog.
- Confusing audit trails with repeated apply receipts.

Additionally, the current receipt format does not include enough information
for an agent starting a new session to determine:
- Whether the workstream has already been applied (skip case).
- Whether the workstream was partially applied and needs completion.
- Whether the apply failed midway and needs rollback before re-apply.

The existing `receipts/live-applies/evidence/` directory stores run logs but
the evidence format is inconsistent across workstreams.

## Decision

### 1. Apply receipt schema

A standardised apply receipt is written to `receipts/live-applies/` on every
apply attempt (success or failure):

```json
{
  "schema_version": 1,
  "receipt_id": "uuid4",
  "workstream": "ws-0346",
  "adr_authority": ["0346", "0349"],
  "environment": "live",
  "agent_session_id": "agent-session-abc123",
  "git_sha": "b980bb92e",
  "repo_version": "0.178.6",

  "phase": "completed",
  "phase_enum": ["pending", "in_progress", "completed", "failed", "partial"],

  "started_at": "2026-04-05T10:00:00Z",
  "completed_at": "2026-04-05T10:04:33Z",
  "duration_seconds": 273,

  "playbooks_run": [
    {"playbook": "playbooks/keycloak.yml", "changed": 3, "failed": 0},
    {"playbook": "playbooks/services/keycloak.yml", "changed": 1, "failed": 0}
  ],

  "services_affected": ["keycloak", "api_gateway_runtime"],
  "vms_affected": [101, 102],

  "outcome": "success",
  "notes": ""
}
```

Receipt file name: `{YYYY-MM-DD}-{workstream}-live-apply.json`.
If multiple attempts exist for the same workstream on the same day,
a `--attempt-N` suffix is appended.

### 2. Idempotency gate

Before starting an apply for workstream `ws-XXXX`, an agent must call:

```
scripts/apply_receipt.py check --workstream ws-XXXX --env live
```

Exit codes per ADR 0343:
- `2` (no-op): receipt exists with `phase: completed` and `outcome: success`.
  Agent should skip the apply entirely or confirm re-apply is intentional.
- `0` (proceed): no receipt, or receipt is `failed`/`partial`. Apply is safe.
- `1` (error): receipt is `in_progress` — another agent is currently applying
  this workstream. Block until the semaphore clears (ADR 0355).

An `in_progress` receipt with `started_at` older than `ttl_seconds` (900 s)
from the apply semaphore is treated as a stale abandoned apply. The gate
transitions it to `failed` and permits a fresh apply.

### 3. Re-apply guard

A completed apply may only be re-applied if the operator explicitly passes
`--force-reapply --reason "..."` to the playbook invocation. This flag is:
- Logged in the new receipt as `forced_reapply: true, force_reason: "..."`.
- Emitted as a mutation audit event (ADR 0354) with severity `warning`.
- Notified via ntfy to the operator.

Automated agents (non-human operators) are prohibited from using `--force-reapply`
without a workstream note documenting the reason.

### 4. Partial apply recovery

A receipt in `phase: partial` indicates the apply completed some playbooks but
not all. The receipt includes which playbooks succeeded in `playbooks_run`.

Recovery protocol:
1. Agent loads the partial receipt.
2. Skips playbooks already in `playbooks_run` with `failed: 0`.
3. Re-runs from the first failed or missing playbook.
4. Writes a new receipt with `phase: completed` referencing the `receipt_id`
   of the partial receipt in `resumed_from_receipt`.

### 5. Receipt index

`receipts/live-applies/.index.yaml` (generated):

```yaml
generated: "2026-04-05"
total_receipts: 412
latest_apply: "2026-04-05T10:04:33Z"
by_workstream:
  ws-0346:
    latest_phase: completed
    latest_outcome: success
    latest_git_sha: b980bb92e
    receipt_file: "2026-04-05-ws-0346-live-apply.json"
by_phase:
  completed: 398
  failed: 8
  partial: 4
  in_progress: 2
```

`scripts/apply_receipt.py index --regen` regenerates this file from all
receipts. Run on every successful apply.

### 6. Workstream status integration

The workstream document (`docs/workstreams/ws-0346.md`) is updated on apply
completion to include:

```markdown
## Live Apply
- **Status:** completed
- **Applied:** 2026-04-05T10:04:33Z
- **Git SHA:** b980bb92e
- **Receipt:** receipts/live-applies/2026-04-05-ws-0346-live-apply.json
- **Agent:** agent-session-abc123
```

This section is written by `scripts/apply_receipt.py update-workstream-doc`.

## Places That Need to Change

### `scripts/apply_receipt.py` (new)

Layer 1 tool per ADR 0345. Commands:
- `check --workstream --env` — idempotency gate.
- `write --workstream --phase --outcome --playbooks-json` — write/update receipt.
- `index --regen` — regenerate `.index.yaml`.
- `update-workstream-doc --workstream` — update workstream markdown.

### `roles/common/tasks/preflight.yml`

Add `apply_receipt.py check` before any apply-phase work.

### All service playbooks (`playbooks/*.yml`)

Add receipt `write --phase in_progress` at start, `write --phase completed|failed`
at end in `always:` block.

### `receipts/live-applies/.index.yaml` (generated)

Regenerated by `apply_receipt.py index --regen` after each apply.

### `Makefile`

Update `live-apply` target to call `apply_receipt.py check` before running
Ansible and `apply_receipt.py update-workstream-doc` after.

### `docs/runbooks/apply-receipts.md` (new)

How to check receipt status, force re-apply, recover from partial apply.

## Consequences

### Positive

- Duplicate applies are blocked automatically — no more accidental double-restarts.
- Partial apply recovery is systematic rather than ad-hoc.
- Receipt index provides instant answer to "has ws-0346 been applied?" without
  reading individual receipt files.
- Workstream documents are automatically updated with apply evidence.

### Negative / Trade-offs

- Every apply playbook must be updated to write receipts — a large but
  mechanical change.
- `in_progress` receipts from crashed agents must be TTL-expired before
  subsequent applies can proceed. 15-minute wait in the worst case.
- File-based receipt storage scales poorly for high-frequency applies
  (hundreds per day). For this single-node homelab, not a concern now.

## Related ADRs

- ADR 0085: IaC Boundary
- ADR 0131: Multi-Agent Handoff Protocol
- ADR 0337: Fork-First Workstream and Worktree Metadata
- ADR 0343: Operator Tool Interface Contract
- ADR 0345: Layered Operator Tool Separation
- ADR 0349: Agent Capability Manifest and Peer Discovery
- ADR 0354: Structured Agent Mutation Audit Log
- ADR 0355: Apply-Phase Serialization via Resource-Group Semaphore
