# Workstream ADR 0128: Platform Health Composite Index

- ADR: [ADR 0128](../adr/0128-platform-health-composite-index.md)
- Title: Aggregate uptime, SLO, drift, incident, maintenance, and mutation signals into one composite health index that can gate platform mutations
- Status: merged
- Implemented In Repo Version: 0.125.0
- Implemented On: 2026-03-24
- Branch: `codex/adr-0128-health-composite-index`
- Worktree: `.worktrees/adr-0128`
- Owner: codex
- Depends On: `adr-0064-health-probe-contracts`, `adr-0080-maintenance-windows`, `adr-0091-drift-detection`, `adr-0096-slo-tracking`, `adr-0113-world-state-materializer`, `adr-0114-incident-triage`, `adr-0115-mutation-ledger`, `adr-0123-service-uptime-contracts`
- Conflicts With: none
- Shared Surfaces: `platform/health/`, `scripts/api_gateway/`, `scripts/lv3_cli.py`, `platform/goal_compiler/`, `config/windmill/scripts/health/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `migrations/0013_health_schema.sql`, `docs/runbooks/health-composite-index.md`

## Scope

- add ADR 0128 and the companion workstream/runbook documentation
- add `platform/health/` with a composite client, signal scoring, and storage-backed refresh/read paths
- add `migrations/0013_health_schema.sql` for `health.composite`
- add the Windmill `refresh_composite` worker and its disabled seed schedule
- make the platform API serve composite health instead of raw world-state-only health
- add `lv3 health` and make the goal compiler reject unsafe health unless explicitly overridden
- verify the composite score against simulated failures in focused tests

## Non-Goals

- live-applying the new Postgres schema or Windmill schedule from this change
- replacing world-state service health, drift receipts, incident triage, or the ledger as source systems
- implementing runtime-tunable signal weights

## Expected Repo Surfaces

- `platform/health/__init__.py`
- `platform/health/composite.py`
- `config/windmill/scripts/health/refresh-composite.py`
- `migrations/0013_health_schema.sql`
- `scripts/api_gateway/main.py`
- `scripts/lv3_cli.py`
- `platform/goal_compiler/compiler.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `tests/test_health_composite.py`
- `tests/test_health_windmill.py`
- `tests/test_health_repo_surfaces.py`
- `tests/test_api_gateway.py`
- `tests/test_lv3_cli.py`
- `tests/unit/test_goal_compiler.py`

## Expected Live Surfaces

- `health.composite` exists in the shared Postgres runtime database after the migration is applied
- Windmill exposes `f/lv3/health/refresh_composite` and can schedule it every minute
- `GET /v1/platform/health` returns composite status, score, safety, and contributing signals
- `lv3 health` reports the same composite state locally
- the goal compiler blocks unsafe service mutations unless the operator explicitly bypasses health

## Verification

- `uv run --with pytest --with httpx --with cryptography --with fastapi --with pydantic --with pyyaml python -m pytest tests/test_health_composite.py tests/test_health_windmill.py tests/test_health_repo_surfaces.py tests/test_api_gateway.py tests/unit/test_goal_compiler.py tests/test_lv3_cli.py -q`

## Merge Criteria

- the composite score persists into the health table refresh path
- simulated probe, drift, incident, and maintenance scenarios classify correctly
- the API and CLI return composite health without breaking existing service status consumers
- goal-compiled service mutations fail with `HEALTH_UNSAFE` unless explicitly bypassed
