# Workstream WS-0209: Runbook Use-Case Service Live Apply

- ADR: [ADR 0209](../adr/0209-use-case-services-and-thin-delivery-adapters.md)
- Title: Shared runbook use-case service with thin delivery adapters for CLI, API gateway, Windmill, and the ops portal
- Status: ready
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0209-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0209-live-apply`
- Owner: codex
- Depends On: `adr-0129-runbook-automation-executor`, `adr-0204-architecture-governance`
- Conflicts With: none
- Shared Surfaces: `platform/use_cases/`, `scripts/runbook_executor.py`, `scripts/api_gateway/main.py`, `scripts/ops_portal/app.py`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`, `config/workflow-catalog.json`, `config/command-catalog.json`, `build/platform-manifest.json`, `docs/runbooks/`, `docs/diagrams/agent-coordination-map.excalidraw`, `tests/`, `receipts/live-applies/`

## Scope

- extract the repo-local runbook orchestration into a shared use-case module under `platform/`
- keep the CLI and Windmill wrapper thin by delegating to that shared use-case service
- expose the same runbook service through the platform API gateway with stable list, execute, status, and approve routes
- switch the ops portal runbook panel to the gateway-backed runbook contract instead of a drifted local workflow model
- add one safe diagnostic structured runbook for live verification and record the branch-local live-apply evidence

## Non-Goals

- redesigning the broader workflow scheduler or goal-compiler contracts
- converting every existing workflow-backed portal action to structured runbooks in one pass
- updating protected integration files on this workstream branch before the mainline merge step

## Expected Repo Surfaces

- `platform/use_cases/runbooks.py`
- `scripts/runbook_executor.py`
- `scripts/api_gateway/main.py`
- `scripts/ops_portal/app.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`
- `Makefile`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `build/platform-manifest.json`
- `docs/runbooks/runbook-automation-executor.md`
- `docs/runbooks/platform-operations-portal.md`
- `docs/runbooks/ops-portal-down.md`
- `docs/runbooks/validation-gate-status.yaml`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/adr/0209-use-case-services-and-thin-delivery-adapters.md`
- `docs/workstreams/ws-0209-live-apply.md`
- `tests/test_api_gateway.py`
- `tests/test_api_gateway_runtime_role.py`
- `tests/test_interactive_ops_portal.py`
- `tests/test_runbook_executor.py`
- `tests/test_runbook_executor_windmill.py`
- `tests/test_validation_gate.py`
- `tests/test_validation_gate_windmill.py`
- `tests/test_windmill_operator_admin_app.py`

## Expected Live Surfaces

- `api.lv3.org` exposes the structured runbook list, execute, status, and approve routes through the API gateway
- `ops.lv3.org` loads its runbook panel from the shared gateway contract instead of a local workflow-only approximation
- the API gateway persists structured runbook records under its durable data directory instead of ephemeral container state

## Verification

- `uv run --with pytest --with pyyaml --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with PyJWT==2.10.1 --with jinja2==3.1.5 --with itsdangerous==2.2.0 --with python-multipart==0.0.20 pytest tests/test_runbook_executor.py tests/test_runbook_executor_windmill.py tests/test_api_gateway.py tests/test_api_gateway_runtime_role.py tests/test_interactive_ops_portal.py tests/test_validation_gate.py tests/test_validation_gate_windmill.py tests/test_windmill_operator_admin_app.py -q`
- `python3 -m py_compile scripts/runbook_executor.py scripts/api_gateway/main.py scripts/ops_portal/app.py platform/use_cases/runbooks.py`
- `make syntax-check-api-gateway`
- `make syntax-check-ops-portal`
- `python3 scripts/generate_diagrams.py --check`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- live verification: list and execute `validation-gate-status` through the gateway, then confirm the same result renders through the ops portal adapter path

## Merge Criteria

- shared runbook orchestration lives in one use-case service instead of being duplicated per delivery surface
- CLI, Windmill, API gateway, and ops portal adapters stay thin and only translate transport-specific input or output
- the branch records a safe live verification receipt without touching protected integration files that belong to the later `main` merge step

## Notes For The Next Assistant

- keep the runbook delivery-surface allowlist explicit; do not implicitly publish every eligible runbook through the portal
- the safest verification path is the read-only `validation-gate-status` runbook; avoid using mutation-oriented runbooks just to prove adapter wiring
