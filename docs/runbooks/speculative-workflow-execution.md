# Speculative Workflow Execution

This runbook documents how to author and use ADR 0159 speculative execution in the repository scheduler.

## Purpose

Use speculative execution only for workflows that are reversible and can prove post-execution consistency with a dedicated probe.

The default scheduler path remains pessimistic. Speculative mode is an explicit workflow opt-in plus an explicit caller opt-in.

## Authoring Checklist

1. Pick a workflow that is reversible at the platform level.
2. Implement or identify a compensating workflow that can undo the forward change.
3. Write a probe callable that can tell whether the speculative result should be kept or rolled back.
4. Add a `speculative` block to the workflow catalog entry.
5. Validate the catalog and run the speculative unit tests before merge.

## Catalog Shape

Add a `speculative` block to the workflow:

```json
{
  "speculative": {
    "eligible": true,
    "compensating_workflow_id": "restore-example-secret",
    "conflict_probe": {
      "path": "platform/scheduler/speculative_hooks.py",
      "callable": "probe_example_secret"
    },
    "probe_delay_seconds": 30,
    "rollback_window_seconds": 300
  }
}
```

## Probe Contract

The probe callable receives one dictionary and must return either:

- `false` for no conflict
- `true` for a generic conflict
- a mapping with:

```json
{
  "conflict_detected": true,
  "winning_intent_id": "intent-123",
  "conflicting_intent_id": "intent-456",
  "message": "existing writer wins",
  "metadata": {
    "field": "value"
  }
}
```

If `winning_intent_id` is omitted or equals the current intent, the scheduler treats the speculative execution as committed.

## Operator Usage

Run speculative mode explicitly:

```bash
lv3 run --allow-speculative "deploy netbox"
```

If the workflow is not eligible, the compiler and scheduler fall back to the ordinary pessimistic path.

## Validation

Run:

```bash
uv run --with pytest --with pyyaml python -m pytest tests/unit/test_goal_compiler.py tests/unit/test_intent_conflicts.py tests/unit/test_scheduler_budgets.py tests/unit/test_ledger_writer.py tests/test_lv3_cli.py -q
uv run --with pyyaml python scripts/workflow_catalog.py --validate
```

## Evidence and State

- speculative runtime state is written to `.local/scheduler/speculative-executions.json`
- scheduler audit events land in the mutation ledger event stream
- the main lifecycle events are:
  - `execution.speculative_started`
  - `execution.speculative_probing`
  - `execution.speculative_committed`
  - `execution.speculative_rolled_back`

## Operational Boundaries

- do not enable speculative mode for filesystem convergence, database migrations, or broad Ansible plays
- do not treat a compensating workflow as trustworthy until it has its own verification path
- do not claim a platform version bump until a speculative-enabled workflow is applied and validated from `main`
