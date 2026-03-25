# Workstream ADR 0164: Circuit Breaker Pattern for External Service Calls

- ADR: [ADR 0164](../adr/0164-circuit-breaker-pattern-for-external-service-calls.md)
- Title: Shared circuit policies and fail-fast dependency guards for Keycloak, Windmill, Ollama, and gateway NATS publishing
- Status: merged
- Implemented In Repo Version: 0.144.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Branch: `codex/live-apply-0164`
- Worktree: `.worktrees/live-apply-0164`
- Owner: codex
- Depends On: `adr-0058-nats-event-bus`, `adr-0092-platform-api-gateway`, `adr-0119-budgeted-workflow-scheduler`, `adr-0129-runbook-automation-executor`, `adr-0145-ollama`
- Conflicts With: none
- Shared Surfaces: `config/circuit-policies.yaml`, `platform/circuit/`, `scripts/api_gateway/main.py`, `platform/llm/client.py`, `platform/scheduler/scheduler.py`, `scripts/runbook_executor.py`, `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/`, `docs/runbooks/circuit-breaker-operations.md`

## Scope

- add a shared `platform/circuit` package with sync and async breakers, policy loading, and memory, file, plus NATS KV-backed state backends
- add `config/circuit-policies.yaml` as the repo-managed circuit contract
- wire Keycloak JWKS fetches, proxied gateway upstream calls, and NATS request-event publishes through the circuit layer
- wire the shared LLM client and Windmill-facing scheduler and runbook executor paths through the same circuit policies
- bundle the circuit policy file into the converged API gateway runtime
- add focused regression coverage for the state machine, LLM fallback, API gateway fail-fast behavior, and Windmill callers
- document operator verification and troubleshooting in a dedicated runbook

## Non-Goals

- full graceful-degradation buffering or queueing from ADR 0167
- retrofitting every historical repo script in one pass
- claiming a platform live rollout before the updated runtime surfaces are actually converged from `main`

## Expected Repo Surfaces

- `config/circuit-policies.yaml`
- `platform/circuit/`
- `scripts/api_gateway/main.py`
- `platform/llm/client.py`
- `platform/scheduler/scheduler.py`
- `scripts/runbook_executor.py`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/api_gateway_runtime/templates/api-gateway.env.j2`
- `docs/runbooks/circuit-breaker-operations.md`
- `docs/adr/0164-circuit-breaker-pattern-for-external-service-calls.md`
- `docs/workstreams/adr-0164-circuit-breaker-pattern.md`
- `tests/test_circuit_breaker.py`
- `tests/test_platform_llm_client.py`
- `tests/test_api_gateway.py`
- `tests/test_windmill_circuit_clients.py`

## Expected Live Surfaces

- none claimed yet; the repository now contains the converge-ready gateway wiring and the shared circuit package, but no live receipt is recorded in this workstream

## Verification

- Run `python3 -m py_compile platform/circuit/__init__.py platform/circuit/breaker.py platform/llm/client.py platform/scheduler/scheduler.py scripts/runbook_executor.py scripts/api_gateway/main.py scripts/validate_repository_data_models.py`
- Run `uv run --with-requirements requirements/api-gateway.txt --with pytest pytest -q tests/test_circuit_breaker.py tests/test_platform_llm_client.py tests/test_api_gateway.py tests/test_windmill_circuit_clients.py`
- Run `uv run --with pytest --with pyyaml pytest -q tests/test_runbook_executor.py tests/unit/test_scheduler_budgets.py tests/test_api_gateway_runtime_role.py`
- Run `uv run --with-requirements requirements/api-gateway.txt --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Merge Criteria

- the shared circuit state machine opens, half-opens, and closes deterministically under test
- the gateway returns dependency-aware `503` responses with `Retry-After` once a circuit is open
- Windmill callers stop repeatedly attempting the same failed dependency once the circuit opens
- the repo-managed API gateway converge path includes the circuit policy file

## Outcome

- repository implementation is complete in release `0.144.0`
- the circuit layer now protects Keycloak JWKS fetches, gateway upstream calls, NATS request-event publishing, the shared LLM client, and the Windmill scheduler and runbook executor paths
- platform version remains unchanged until a live deployment is converged from `main` and captured with a receipt
