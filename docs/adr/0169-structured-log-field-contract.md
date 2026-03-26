# ADR 0169: Structured Log Field Contract

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.146.1
- Implemented In Platform Version: 0.130.8
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

The platform collects logs from all services into Loki (ADR 0052) via Promtail. Grafana provides log query and correlation. However, the usefulness of centralised logging depends on the ability to correlate log lines across services, so an operator can follow one platform event from the API gateway through Windmill, Ansible, and verification.

The missing piece was a stable field contract:

- API gateway requests did not emit structured JSON
- platform-context responses did not emit structured JSON
- Windmill promotion workflows did not preserve a shared `trace_id`
- Ansible task output was not queryable as structured JSON

The result was Loki data with no reliable cross-service join key.

## Decision

We standardise structured JSON logging for platform-managed runtime code and execution entrypoints.

### Mandatory fields

Every platform-managed structured log line must include:

```json
{
  "ts": "2026-03-25T11:02:03.456Z",
  "level": "INFO",
  "service_id": "api_gateway",
  "component": "http",
  "trace_id": "a1b2c3d4e5f6",
  "msg": "Request completed",
  "vm": "docker-runtime-lv3"
}
```

Recommended fields when available:

- `intent_id`
- `actor_id`
- `workflow_id`
- `duration_ms`
- `error_code`
- `target`

### Propagation rules

- the API gateway accepts `X-Trace-Id`, generates one if absent, echoes it on responses, and forwards it downstream
- Windmill promotion wrappers preserve `PLATFORM_TRACE_ID`
- Make targets for live apply and targeted converge inject `platform_trace_id` into Ansible
- Ansible emits structured task logs through a repo-managed callback

### Validation

- `scripts/log_validator.py` validates individual JSON log lines or Docker log output
- focused regression tests enforce the contract on the shared logger, validator, callback plugin, gateway propagation, and platform-context API responses

## Consequences

Positive:

- a single `trace_id` now links API gateway requests, promotion automation, Ansible task logs, and downstream service logs
- operators can validate runtime log output with a repo-managed tool instead of ad hoc parsing
- long-running platform services now share one logging implementation instead of bespoke formats

Trade-offs:

- background startup logs still use a synthetic `trace_id` such as `background` or `startup` when no request or workflow context exists
- the first implementation covers the platform-managed runtime path, not every one-shot script or third-party application log

## Boundaries

- this ADR applies to platform-managed Python services, Windmill execution wrappers, and repo-managed Ansible execution paths
- third-party application logs are outside the contract unless the platform explicitly normalises them

## Implementation

- repository runtime code now ships the shared logger in [`platform/logging/__init__.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/logging/__init__.py)
- structured request logging and `X-Trace-Id` propagation are implemented in [`scripts/api_gateway/main.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/api_gateway/main.py) and [`scripts/platform_context_service.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/platform_context_service.py)
- Windmill promotion surfaces preserve trace context in [`config/windmill/scripts/deploy-and-promote.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/deploy-and-promote.py) and [`scripts/promotion_pipeline.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/promotion_pipeline.py)
- live-apply and converge entrypoints inject `platform_trace_id` through [`Makefile`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) and [`inventory/group_vars/all.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/group_vars/all.yml)
- Ansible emits structured task logs through [`collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/collections/ansible_collections/lv3/platform/plugins/callback/structured_log.py)
- the contract validator ships as [`scripts/log_validator.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/log_validator.py)
- the production platform-context runtime was verified live from `main` in [`receipts/live-applies/2026-03-26-adr-0169-structured-log-contract-live-apply.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/receipts/live-applies/2026-03-26-adr-0169-structured-log-contract-live-apply.json)

## Related ADRs

- ADR 0052: Grafana Loki
- ADR 0075: Service capability catalog
- ADR 0092: Platform API gateway
- ADR 0123: Agent session bootstrap
- ADR 0166: Canonical error response format and error code registry
