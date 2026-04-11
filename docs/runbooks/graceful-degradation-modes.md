# Graceful Degradation Modes

## Purpose

Use this runbook to review declared degradation modes, inspect the current live degraded state, and verify that the platform API gateway is following ADR 0167 instead of failing ambiguously.

## Repo Surfaces

- `config/service-capability-catalog.json`
- `docs/schema/service-capability-catalog.schema.json`
- `platform/degradation/state.py`
- `platform/health/composite.py`
- `scripts/api_gateway/main.py`

## Validate The Declarations

```bash
uv run --with pyyaml --with jsonschema python scripts/service_catalog.py --validate
python3 scripts/service_catalog.py --service api_gateway
python3 scripts/service_catalog.py --service windmill
python3 scripts/service_catalog.py --service openbao
```

Expected:

- the catalog validates cleanly
- `show-service` prints a `Degradation modes:` section for services that declare ADR 0167 behaviour

## Inspect Live Gateway Degradation State

On `docker-runtime`:

```bash
sudo cat /opt/api-gateway/data/degradation-state.json
sudo test -f /opt/api-gateway/data/nats-outbox.jsonl && sudo cat /opt/api-gateway/data/nats-outbox.jsonl || true
```

Expected:

- `degradation-state.json` is absent or contains an empty `services` object during normal operation
- `nats-outbox.jsonl` is absent during normal operation

## Query Through The Gateway

From an operator workstation with a valid platform token:

```bash
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.example.com/v1/platform/services | jq '.services[] | select(.id=="api_gateway") | {id, degradation_modes, active_degradations}'
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.example.com/v1/platform/degradations | jq
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.example.com/v1/platform/health | jq '.services[] | select(.service_id=="api_gateway") | {service_id, composite_status, active_degradations}'
```

Expected:

- the `api_gateway` service entry shows the declared `keycloak` and `nats` degradation modes
- `/v1/platform/degradations` reports zero active degradations during steady state
- the health payload shows `active_degradations: []` for `api_gateway` during steady state

## Verify Keycloak Graceful Degradation

1. Confirm the gateway has a warm JWKS cache by calling any authenticated `/v1/*` endpoint once.
2. Temporarily make the Keycloak JWKS endpoint unreachable from the gateway container.
3. Re-run an authenticated gateway request before the cached JWKS expires.

Expected:

- authenticated requests continue to succeed while the cached JWKS remains valid
- `/v1/platform/degradations` reports an active `keycloak` degradation for `api_gateway`
- once the cache expires, authenticated requests fail fast with `503` and `Retry-After: 30` instead of timing out or returning an ambiguous `401`

## Recovery

- restore Keycloak reachability
- issue another authenticated gateway request to force a JWKS refresh
- confirm `/v1/platform/degradations` is empty again
- if `nats-outbox.jsonl` exists, confirm it drains after NATS publication succeeds again
