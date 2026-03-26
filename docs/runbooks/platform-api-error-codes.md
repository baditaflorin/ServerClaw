# Platform API Error Codes

## Purpose

Document the canonical error envelope and the error code registry used by repo-managed platform HTTP APIs.

## Source Of Truth

- Registry: `config/error-codes.yaml`
- Shared implementation: `scripts/canonical_errors.py`
- Live HTTP surfaces:
  - `scripts/api_gateway/main.py`
  - `scripts/platform_context_service.py`

## Canonical Envelope

All repo-managed platform HTTP errors now return:

```json
{
  "error": {
    "code": "INPUT_UNKNOWN_WORKFLOW",
    "message": "Unknown workflow: deploy-foo",
    "trace_id": "8d441eb8-2f7a-4517-a927-e7d0742d60cf",
    "retry_advice": "none",
    "retry_after": null,
    "docs_url": "https://github.com/baditaflorin/proxmox_florin_server/blob/main/docs/runbooks/platform-api-error-codes.md",
    "occurred_at": "2026-03-25T10:00:00+00:00",
    "context": {
      "workflow_id": "deploy-foo"
    }
  }
}
```

## Operator Verification

API gateway:

```bash
curl -s http://127.0.0.1:8083/v1/health | jq .
curl -s http://127.0.0.1:8083/v1/unknown | jq .
```

Platform context API:

```bash
curl -s http://127.0.0.1:8010/v1/platform-summary | jq .
curl -s -H "Authorization: Bearer $PLATFORM_CONTEXT_API_TOKEN" http://127.0.0.1:8010/v1/workflows/missing | jq .
```

Expected:

- anonymous protected requests return `AUTH_TOKEN_MISSING`
- invalid or expired credentials return `AUTH_TOKEN_INVALID` or `AUTH_TOKEN_EXPIRED`
- missing routes or resources return `INPUT_*` codes
- dependency or runtime outages return `INFRA_*` codes

## Maintenance Rules

- `config/error-codes.yaml` is append-only; do not repurpose an existing code.
- Add new codes before wiring them into a runtime surface.
- Keep `message` human-readable and stable enough for operators, but treat only `error.code` as the machine contract.
