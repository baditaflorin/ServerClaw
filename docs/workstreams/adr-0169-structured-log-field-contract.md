# Workstream ADR 0169: Structured Log Field Contract

- ADR: [ADR 0169](../adr/0169-structured-log-field-contract.md)
- Title: shared JSON logging, trace propagation, structured Ansible task logs, and validator coverage
- Status: live_applied
- Branch: `codex/live-apply-0169`
- Worktree: `.worktrees/adr-0169`
- Owner: codex
- Depends On: `adr-0052-loki-logs`, `adr-0075-service-capability-catalog`, `adr-0092-platform-api-gateway`, `adr-0123-service-uptime-contracts`, `adr-0166-canonical-error-response-format`
- Conflicts With: none
- Shared Surfaces: `platform/`, `scripts/api_gateway/`, `scripts/platform_context_service.py`, `scripts/promotion_pipeline.py`, `config/windmill/scripts/`, `collections/ansible_collections/lv3/platform/plugins/callback/`, `Makefile`, `inventory/group_vars/all.yml`, `docs/runbooks/`

## Scope

- add a shared structured JSON logger for platform-managed Python services
- propagate `trace_id` through the API gateway, platform-context API, Windmill promotion wrapper, and live-apply entrypoints
- emit structured JSON task logs from Ansible with a repo-managed callback plugin
- add a log-contract validator CLI and regression coverage for the logging path
- apply the changed runtime surfaces live on the production docker runtime VM from `main`

## Non-Goals

- retrofitting every historical one-shot script in the repository to structured logging in one turn
- normalising third-party application logs that remain outside the platform-managed contract boundary
- replacing Loki or Alloy with a new logging stack

## Expected Repo Surfaces

- `platform/logging/__init__.py`
- `scripts/api_gateway/main.py`
- `scripts/platform_context_service.py`
- `scripts/promotion_pipeline.py`
- `config/windmill/scripts/deploy-and-promote.py`
- `scripts/log_validator.py`
- `collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py`
- `Makefile`
- `inventory/group_vars/all.yml`
- `ansible.cfg`
- `docs/runbooks/structured-log-contract.md`
- `tests/test_platform_logging.py`
- `tests/test_log_validator.py`
- `tests/test_structured_log_callback.py`

## Expected Live Surfaces

- `api-gateway` emits structured JSON request logs and forwards `X-Trace-Id` downstream
- `platform-context-api` emits structured JSON request and query logs and echoes `X-Trace-Id`
- live applies inject `platform_trace_id` into Ansible runs and emit structured task-level log lines

## Verification

- `uv run --with pytest==8.4.2 --with fastapi==0.116.1 --with httpx==0.28.1 --with cryptography==45.0.6 --with qdrant-client==1.15.1 --with PyYAML==6.0.2 pytest -q tests/test_platform_logging.py tests/test_log_validator.py tests/test_structured_log_callback.py tests/test_deploy_and_promote_windmill.py tests/test_api_gateway.py tests/test_platform_context_service.py`
- `./scripts/validate_repo.sh ansible-syntax yaml`
- live API gateway smoke request with an explicit `X-Trace-Id`
- live platform-context request plus `scripts/log_validator.py` against recent container logs

## Merge Criteria

- every touched runtime surface emits the mandatory ADR 0169 fields
- proxied requests preserve the inbound `X-Trace-Id`
- Ansible task logs are emitted in structured JSON during live apply
- the validator rejects malformed lines and accepts structured runtime output

## Outcome

- repository implementation shipped in `0.146.1`
- platform runtime applied from `main` in platform version `0.130.4`
- production docker-runtime surfaces now emit repo-managed structured JSON logs with propagated `trace_id`
