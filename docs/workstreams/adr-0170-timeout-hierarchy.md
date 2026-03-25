# Workstream ADR 0170: Platform-Wide Timeout Hierarchy

- ADR: [ADR 0170](../adr/0170-platform-wide-timeout-hierarchy.md)
- Title: Canonical timeout hierarchy, deadline propagation helpers, validation, and runtime integration
- Status: merged
- Branch: `codex/adr-0170-timeout-hierarchy`
- Worktree: `../proxmox_florin_server-timeout-hierarchy`
- Owner: codex
- Depends On: `adr-0092-platform-api-gateway`, `adr-0113-world-state-materializer`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: `adr-0092-platform-api-gateway` (shared gateway runtime and catalog), `adr-0119-budgeted-workflow-scheduler` (shared watchdog path), `adr-0113-world-state-materializer` (shared worker timeouts)
- Shared Surfaces: `config/timeout-hierarchy.yaml`, `platform/timeouts/`, `scripts/api_gateway/main.py`, `platform/scheduler/`, `platform/world_state/workers.py`, `scripts/drift_lib.py`, `scripts/netbox_inventory_sync.py`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`, `config/workflow-catalog.json`, `docs/runbooks/platform-timeout-hierarchy.md`

## Scope

- create `config/timeout-hierarchy.yaml`
- create `platform/timeouts/` for hierarchy loading and deadline propagation
- create validation and hardcoded-timeout scanning scripts
- wire timeout enforcement into the API gateway, scheduler, world-state workers, SSH helper library, and NetBox sync
- align timeout hierarchy with the existing ADR 0172 live watchdog path
- document validation and live-apply procedure

## Verification

- `uv run --with pyyaml python scripts/validate_timeout_hierarchy.py`
- `python3 scripts/check_hardcoded_timeouts.py`
- `uv run --with pytest --with pyyaml --with httpx==0.28.1 --with fastapi==0.116.1 --with cryptography==45.0.6 pytest tests/test_timeout_hierarchy.py tests/test_api_gateway.py tests/test_world_state_workers.py tests/unit/test_scheduler_budgets.py -q`
- live replay of the API gateway and Windmill converges

## Notes For The Next Assistant

- `origin/main` advanced during implementation and already included ADR 0172 by the time this workstream was integrated.
- The timeout hierarchy is intentionally based on current committed maxima rather than the earlier draft’s inconsistent sample numbers.
