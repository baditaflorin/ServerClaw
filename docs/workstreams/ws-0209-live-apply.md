# Workstream WS-0209: Runbook Use-Case Service Live Apply

- ADR: [ADR 0209](../adr/0209-use-case-services-and-thin-delivery-adapters.md)
- Title: Shared runbook use-case service with thin delivery adapters for CLI, API gateway, Windmill, and the ops portal
- Status: live_applied
- Implemented In Repo Version: 0.177.38
- Live Applied In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0209-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0209-live-apply`
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

- `api.example.com` exposes the structured runbook list, execute, status, and approve routes through the API gateway
- `ops.example.com` loads its runbook panel from the shared gateway contract instead of a local workflow-only approximation
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

## Outcome

- the shared runbook orchestration now lives in [`platform/use_cases/runbooks.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/use_cases/runbooks.py), with the CLI, Windmill wrapper, API gateway, and ops portal each reduced to thin surface adapters over the same delivery contract
- the rebased live apply re-converged `api_gateway`, `ops_portal`, and `windmill` from the isolated worktree, and the safe `validation-gate-status` runbook now verifies successfully through all three live paths
- the workstream also repaired a rebased Windmill topology regression on the branch by switching the runtime defaults back to the host-level port facts actually available in the play context and documenting the guest-local probe endpoints used during verification

## Mainline Integration

- release `0.177.38` now carries the official repo-version attribution for ADR 0209 on `main`
- the integrated canonical truth now records `versions/stack.yaml` repo version `0.177.38`, platform version `0.130.38`, and maps `api_gateway`, `ops_portal`, and `windmill` to receipt `2026-03-28-adr-0209-use-case-services-live-apply`
- the protected integration files were updated on this branch because the workstream became the final verified integration step: `README.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.38.md`, and `versions/stack.yaml`

## Notes For The Next Assistant

- keep the runbook delivery-surface allowlist explicit; do not implicitly publish every eligible runbook through the portal
- the safest verification path is the read-only `validation-gate-status` runbook; avoid using mutation-oriented runbooks just to prove adapter wiring
- `./scripts/validate_repo.sh agent-standards` was re-run while `workstreams.yaml` still marked this branch `ready`; after the final status flip to `live_applied`, that validator is expected to reject the branch because terminal workstreams are no longer considered active branch owners
- direct SSH verification from `docker-runtime` should use the guest-local listeners `http://127.0.0.1:8083` for the API gateway and `http://127.0.0.1:8000` for Windmill; `http://100.64.0.1:8005` is the Proxmox-host proxy, not the guest-local bind
- the successful live replay proved the worker-checkout integrity refresh against the earlier stale Windmill checkout drift, even though long-running unrelated Windmill playbook processes from other workstreams were still visible on the controller during this branch
