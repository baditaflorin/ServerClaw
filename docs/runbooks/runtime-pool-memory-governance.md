# Runtime Pool Memory Governance

## Purpose

Document the repo-managed memory envelope and host headroom procedure for
`runtime-control`, `runtime-general`, and `runtime-ai` under ADR 0321.

## Source Of Truth

- `config/capacity-model.json`
  - `guests[]` for current VM allocations and budgets
  - `runtime_pool_memory` for the approved pool baselines, maxima, and host
    free-memory floor
- `config/service-capability-catalog.json` for the declared `runtime_pool`
  assignments
- `scripts/capacity_report.py` for the operator-readable and machine-readable
  validation view

## Update Procedure

1. Update service placement first.
   - Confirm the affected services already point at the intended
     `runtime_pool` in `config/service-capability-catalog.json`.

2. Update the runtime guest shape if needed.
   - Adjust the relevant guest `allocated` or `budget` values in
     `config/capacity-model.json`.

3. Update the governed pool envelope.
   - Edit `config/capacity-model.json.runtime_pool_memory`.
   - Keep `runtime-control` first in `admission_priority`.
   - Keep the combined runtime-pool baseline at or above `40 GiB`.
   - Keep the combined runtime-pool max at or below `64 GiB`.
   - Keep the host free-memory floor at or above `20 GiB`.

4. Regenerate derived platform vars.

```bash
uv run --with pyyaml python scripts/generate_platform_vars.py --write
```

5. Validate the contract.

```bash
uv run --with pytest pytest \
  tests/test_capacity_report.py \
  tests/test_generate_platform_vars.py \
  tests/test_runtime_pool_service_classification.py

scripts/validate_repo.sh data-models
```

## Verification

Inspect the governed pool view without live metrics:

```bash
python3 scripts/capacity_report.py --no-live-metrics --format text
```

Inspect the machine-readable output:

```bash
python3 scripts/capacity_report.py --no-live-metrics --format json
```

The output should include:

- `runtime_pool_memory.combined_baseline_ram_gb`
- `runtime_pool_memory.combined_max_ram_gb`
- `runtime_pool_memory.remaining_ram_after_pool_max_gb`
- one entry per governed runtime pool with its admission priority

## Guardrails

- Do not add a new `runtime-*` pool in the service catalog without adding a
  matching entry under `runtime_pool_memory`.
- Do not lower the host free-memory floor below `20 GiB`.
- Do not raise the combined pool max above `64 GiB` without a new ADR or ADR
  amendment.
- Treat `scripts/validate_repo.sh data-models` failures as contract drift, not
  as optional warnings.
