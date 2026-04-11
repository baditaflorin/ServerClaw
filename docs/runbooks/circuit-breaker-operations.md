# Circuit Breaker Operations

ADR 0164 adds repo-managed circuit breaker policies for external and high-impact internal dependency calls.

## Repo Surfaces

- policy file: `config/circuit-policies.yaml`
- shared runtime package: `platform/circuit/`
- current integrated callers:
  - `scripts/api_gateway/main.py`
  - `platform/llm/client.py`
  - `platform/scheduler/scheduler.py`
  - `scripts/runbook_executor.py`

## State Backends

- preferred distributed backend: NATS JetStream KV when `LV3_NATS_URL` or `LV3_CIRCUIT_STATE_NATS_URL` is configured
- optional shared local backend: JSON file when `LV3_CIRCUIT_STATE_FILE` is set
- default fallback: local in-memory state inside the process

If the NATS KV backend cannot be reached, the runtime falls back to local state instead of blocking startup.

## Validate The Contract

Run the repository checks before merge or before a converge:

```bash
python3 -m py_compile \
  platform/circuit/__init__.py \
  platform/circuit/breaker.py \
  platform/llm/client.py \
  platform/scheduler/scheduler.py \
  scripts/runbook_executor.py \
  scripts/api_gateway/main.py

uv run --with-requirements requirements/api-gateway.txt --with pytest pytest -q \
  tests/test_circuit_breaker.py \
  tests/test_platform_llm_client.py \
  tests/test_api_gateway.py \
  tests/test_windmill_circuit_clients.py

uv run --with-requirements requirements/api-gateway.txt --with pyyaml --with jsonschema \
  python scripts/validate_repository_data_models.py --validate
```

## Verify Gateway Behaviour

Normal path:

```bash
curl -sS -H "Authorization: Bearer <token>" https://api.example.com/v1/health | jq .
```

When Keycloak or a proxied upstream dependency is unavailable:

- the first dependency failure is surfaced as a `503` or `502`
- once the circuit is open, repeated requests return `503`
- open-circuit responses include `Retry-After`

## Troubleshooting

- inspect the policy values first; overly aggressive thresholds create false opens
- if a circuit is open, prefer waiting for the declared recovery window and allowing the half-open probe to close it naturally
- for the API gateway runtime, confirm `/config/circuit-policies.yaml` exists in the deployed config bundle after converge
- if file-backed state is used for a local harness, inspect the JSON file referenced by `LV3_CIRCUIT_STATE_FILE`
- if NATS-backed state is expected, verify the `platform-circuits` KV bucket is reachable from the runtime before debugging caller code

## Recovery

- restore the failed dependency first; do not clear the circuit while the dependency is still down
- restart the affected runtime only if you need to clear local in-memory state immediately
- if file-backed state is used for a local test harness, remove or edit the specific circuit entry only after the dependency is healthy again
