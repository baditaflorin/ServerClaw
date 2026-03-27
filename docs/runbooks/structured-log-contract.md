# Structured Log Contract

## Purpose

This runbook defines how to emit, validate, and verify the ADR 0169 structured log contract on the live platform.

## Canonical Sources

- ADR: [ADR 0169](../adr/0169-structured-log-field-contract.md)
- shared logger: [platform/logging/__init__.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/logging/__init__.py)
- validator CLI: [scripts/log_validator.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/log_validator.py)
- Ansible callback: [collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py)

## Required Fields

Every platform-managed structured log line must include:

- `ts`
- `level`
- `service_id`
- `component`
- `trace_id`
- `msg`
- `vm`

Recommended fields when available:

- `intent_id`
- `actor_id`
- `workflow_id`
- `duration_ms`
- `error_code`
- `target`

## Operator Workflow

For Python services:

- use `get_logger(service_id, component)` from `platform.logging`
- bind `trace_id` at the request or job boundary
- pass structured values through `extra={...}` instead of embedding them into the message string

For live apply and converge commands:

- export `PLATFORM_TRACE_ID=<trace-id>` when driving Ansible directly
- the repo `Makefile` forwards `platform_trace_id` into playbooks
- the structured Ansible callback emits task-level JSON logs automatically when `ansible.cfg` is in use

## Validation

Validate a captured log file:

```bash
python3 scripts/log_validator.py /path/to/log.jsonl --report-json
```

Validate Docker JSON log output:

```bash
docker logs api-gateway --tail 50 2>&1 | python3 scripts/log_validator.py --report-json
```

Run the focused regression suite:

```bash
uv run --with pytest==8.4.2 --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with qdrant-client==1.15.1 --with PyYAML==6.0.2 pytest -q tests/test_platform_logging.py tests/test_log_validator.py tests/test_structured_log_callback.py tests/test_deploy_and_promote_windmill.py tests/test_api_gateway.py tests/test_platform_context_service.py
```

## Live Verification

After a production apply:

1. request the API gateway with an explicit `X-Trace-Id`
2. confirm the response echoes the same `X-Trace-Id`
3. inspect the relevant container logs and validate them with `scripts/log_validator.py`
4. if the request fans into downstream services, confirm the same `trace_id` appears there as well

Example:

```bash
TRACE_ID=adr0169-smoke-001
curl -fsS -H "Authorization: Bearer $(cat .local/platform-context/api-token.txt)" -H "X-Trace-Id: ${TRACE_ID}" http://10.10.10.20:8010/v1/platform-summary >/dev/null
sudo docker logs platform-context-api --tail 20 2>&1 | python3 scripts/log_validator.py --report-json
```
