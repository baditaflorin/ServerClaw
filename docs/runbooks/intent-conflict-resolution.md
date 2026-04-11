# Intent Conflict Resolution

## Purpose

This runbook covers the ADR 0127 intent conflict gate: claim inference, duplicate suppression, conflict rejection, and the controller-local registry used to coordinate concurrent worktrees and local agents.

## Canonical Sources

- ADR: [docs/adr/0127-intent-deduplication-and-conflict-resolution.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0127-intent-deduplication-and-conflict-resolution.md)
- registry engine: [platform/conflict/engine.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/conflict/engine.py)
- scheduler integration: [platform/scheduler/scheduler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/scheduler/scheduler.py)
- CLI surface: [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/lv3_cli.py)
- workflow metadata: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json)

## How It Works

1. The scheduler infers resource claims from `config/workflow-catalog.json`.
2. It acquires the atomic conflict registry lock.
3. It checks for:
   - recent completed duplicates
   - active write conflicts on the same resource
   - active dependency writes that should be surfaced as warnings
4. On a clear result it records `intent.claim_registered` and submits to Windmill.
5. On completion it releases the active claim and preserves successful entries for the workflow's dedup window.

## Operator Preview

Use the preview command before submitting a manual action:

```bash
lv3 intent check deploy netbox
lv3 intent check converge-netbox --args service=netbox
```

Expected output includes:

- inferred resource claims
- `CLEAR`, `CONFLICT`, or `DUPLICATE`
- the conflicting intent ID when blocked
- cascade warnings when a direct dependency is already mid-change

## Registry Location

Default behavior:

- if the checkout is a git worktree, the registry lives under the git common directory so sibling worktrees share one view
- otherwise it falls back to `.local/state/conflicts/registry.json` under the repo root

Override for testing or recovery:

```bash
export LV3_CONFLICT_STATE_PATH=/tmp/lv3-conflicts.json
```

## Dedup Windows

- mutation workflows default to 300 seconds unless `dedup_window_seconds` overrides them
- diagnostic workflows default to `0`

To inspect one workflow's metadata:

```bash
uv run --with pyyaml python scripts/workflow_catalog.py --workflow converge-netbox
```

## Stale-Claim Recovery

Claims expire after `max_duration_seconds + 60`.

If a local test run leaves stale coordination state behind, remove only the registry file for that sandboxed path:

```bash
rm -f .local/state/conflicts/registry.json .local/state/conflicts/registry.lock
```

For shared worktree state, prefer waiting for TTL expiry unless you have verified there is no active scheduler process still running.

## Verification

```bash
uv run --with pytest python -m pytest tests/unit/test_intent_conflicts.py tests/unit/test_scheduler_budgets.py -q
uv run --with pyyaml python scripts/workflow_catalog.py --validate
```
