# Configure Runtime Pool Autoscaling

## Purpose

Document the repo-managed autoscaling policy contract for ADR 0322 before live
Nomad Autoscaler rollout.

## Source Of Truth

- `config/runtime-pool-autoscaling.json` for the autoscaling controller and
  pool policies
- `docs/schema/runtime-pool-autoscaling.schema.json` for the catalog shape
- `config/capacity-model.json.runtime_pool_memory` for pool memory bounds
- `config/service-capability-catalog.json` for autoscaling-eligible
  `mobility_tier` values
- `config/execution-lanes.yaml` for the lanes that pause autoscaling during
  active deploy or migration work
- `scripts/runtime_pool_autoscaling.py` for policy validation and summary

## First-Phase Bounds

The current repo contract allows autoscaling only for:

- `runtime-general`
- `runtime-ai`

The current guarded defaults are:

- scale out at `75%` working-set utilisation sustained for `10` minutes
- scale in below `55%` sustained utilisation after a `60` minute cooldown
- `min_instances=1`, `max_instances=2`
- required signals:
  - `available_memory_percent`
  - `memory_pressure_stall`
  - `swap_activity`
  - `oom_or_restart_evidence`

## Update Procedure

1. Confirm the pool is eligible.
   - The pool must already exist under `config/capacity-model.json.runtime_pool_memory`.
   - At least one service in that pool must have `mobility_tier` set to
     `elastic_stateless` or `burst_batch`.

2. Update `config/runtime-pool-autoscaling.json`.
   - Keep `preferred_implementation` as `nomad-autoscaler`.
   - Keep `metrics_source` as `prometheus`.
   - Keep `routing_surface` as `traefik`.
   - Keep `invocation_surface` as `dapr`.
   - Keep the pause lanes aligned with the pool lane ids in
     `config/execution-lanes.yaml`.

3. Validate the autoscaling policy directly.

```bash
uv run --with pyyaml python scripts/runtime_pool_autoscaling.py --check
uv run --with pyyaml python scripts/runtime_pool_autoscaling.py --json
```

4. Run the repo gate.

```bash
uv run --with pytest pytest tests/test_runtime_pool_autoscaling.py
scripts/validate_repo.sh data-models
```

## Receipts

Scale-action receipts belong under:

- `receipts/runtime-pool-scaling/`

No live receipts should be committed until the controller is actually replayed
from `main`.

## Guardrails

- Do not add `runtime-control` to the autoscaling catalog in the first phase.
- Do not loosen the thresholds or instance bounds without updating ADR 0322 or
  recording a reviewed follow-up decision.
- Do not treat `movable_singleton` or `anchor` services as autoscaling-eligible
  just to satisfy the policy gate. Reclassify them only when the service really
  becomes safe to scale.
