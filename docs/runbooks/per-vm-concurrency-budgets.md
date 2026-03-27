# Per-VM Concurrency Budgets

## Purpose

This runbook covers ADR 0157: the per-lane admission budget enforced before mutation workflows are submitted to Windmill.

## Canonical Sources

- execution-lane catalog: [config/execution-lanes.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/execution-lanes.yaml)
- workflow reservation catalog: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- reservation defaults: [config/workflow-defaults.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-defaults.yaml)
- scheduler implementation: [platform/scheduler/lanes.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/lanes.py)
- scheduler entrypoint: [platform/scheduler/scheduler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/scheduler/scheduler.py)

## Inspection

List the lane catalog:

```bash
make execution-lanes
```

Inspect one lane:

```bash
make execution-lane-info LANE=lane:docker-runtime
```

Inspect one workflow reservation:

```bash
python3 scripts/workflow_catalog.py --workflow converge-windmill
```

Inspect active local reservations:

```bash
cat .local/scheduler/lane-reservations.json
```

## Tuning Rules

Adjust the workflow estimate when:

- a workflow regularly soft-exceeds the lane budget even when the VM is healthy
- operators observe that a workflow is materially lighter than its current reservation and it blocks unrelated work

Adjust the lane budget when:

- the VM has more or less safe headroom for agent-driven mutations than the current lane envelope allows
- the lane policy should change from `soft` to `hard` or vice versa

When editing either surface, keep these constraints:

- prefer changing the narrowest workflow estimate before widening the shared lane budget
- keep `max_concurrent_ops` conservative for stateful or host-level lanes
- use `lane:platform` only when the workflow cannot be tied to one VM lane

## Verification

Run after editing the budget model:

```bash
python3 scripts/execution_lanes.py --validate
python3 scripts/workflow_catalog.py --validate
uv run --with pytest python -m pytest tests/unit/test_scheduler_budgets.py -q
make validate
```
