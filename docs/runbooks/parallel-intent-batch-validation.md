# Parallel Intent Batch Validation

## Purpose

This runbook covers ADR 0160: compile multiple instructions into one batch, fan out semantic dry-runs in parallel, and review the staged execution plan before any batch reaches the scheduler.

## Canonical Sources

- ADR: [docs/adr/0160-parallel-dry-run-fan-out-for-intent-batch-validation.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0160-parallel-dry-run-fan-out-for-intent-batch-validation.md)
- batch planner: [platform/goal_compiler/batch.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/goal_compiler/batch.py)
- compiler entry point: [platform/goal_compiler/compiler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/goal_compiler/compiler.py)
- CLI surface: [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/lv3_cli.py)
- ledger event registry: [config/ledger-event-types.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/ledger-event-types.yaml)

## Preview A Batch

Use one `--instruction` flag per intent:

```bash
lv3 intent batch \
  --instruction "deploy netbox" \
  --instruction "restart-netbox"
```

Optional flags:

- `--max-parallelism 3` to cap concurrent dry-runs
- `--actor-id agent/triage-loop --autonomous` to apply actor policy bounds
- `--force-unsafe-health` to keep an otherwise blocked batch explicit for review
- `--json` for machine-readable output

## Output Interpretation

The batch preview shows:

- `Dry-run failures`: intents that could not produce a semantic diff and were rejected immediately
- `Cross-intent analysis`: the combined-diff classification for shared resources
- `Execution stages`: the safe-parallel and ordered stages derived from those dependencies
- `Rejected intents`: blocking conflicts such as `write_write_conflict`

Current classifications:

- `write_write_conflict`: reject the later intent in submitted order
- `read_after_write_dependency`: stage the writer before the reader
- `restart_during_config`: stage the configuration change before the restart

## Ledger Evidence

When the preview runs through the CLI, it writes `intent.batch_plan` to the configured ledger sink or the local file-backed default under:

```text
.local/state/ledger/ledger.events.jsonl
```

The event stores:

- the combined resource-touch map as `before_state`
- the staged execution plan as `after_state`
- batch metadata such as instruction count and dry-run parallelism

## Verification

```bash
uv run --with pytest --with pyyaml python -m pytest \
  tests/unit/test_goal_compiler.py \
  tests/unit/test_intent_batch_planner.py \
  tests/test_lv3_cli.py -q
```

```bash
uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate
```

## Notes

- This is a planning surface only. The current repository implementation does not yet dispatch staged batch plans through ADR 0155's intent queue.
- The feature is repository-side. No platform version bump should be claimed until a future workstream wires batch execution into the live control plane from `main`.
