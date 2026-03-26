# Configure API Gateway

## Purpose

Converge the repo-managed unified platform API gateway on `docker-runtime-lv3` and publish it on `api.lv3.org`.

## Entry Points

- Playbook: `playbooks/api-gateway.yml`
- Service wrapper: `playbooks/services/api-gateway.yml`
- Health probe id: `api_gateway`
- Catalog: `config/api-gateway-catalog.json`
- Timeout hierarchy: `config/timeout-hierarchy.yaml`

## Local Validation

```bash
python3 scripts/api_gateway_catalog.py --validate
uv run --with pyyaml python scripts/validate_timeout_hierarchy.py
uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 pytest tests/test_api_gateway.py tests/test_api_gateway_catalog.py
```

## Converge

```bash
ansible-playbook -i inventory/hosts.yml playbooks/api-gateway.yml
```

If the controller cannot reach guests directly over Tailscale, use the Proxmox jump path:

```bash
ansible-playbook -i inventory/hosts.yml -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/api-gateway.yml
```

## Verify

From `docker-runtime-lv3`:

```bash
curl -sf http://127.0.0.1:8083/healthz
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8083/v1/health
test -f /opt/api-gateway/config/timeout-hierarchy.yaml
```

Expected:

- `/healthz` returns `200`
- `/v1/health` returns `401` with `error.code=AUTH_TOKEN_MISSING` without a bearer token

From an operator workstation with a valid Keycloak token:

```bash
curl https://api.lv3.org/healthz
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/health
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/platform/services
```

## Notes

- The gateway validates Keycloak JWTs directly against the realm JWKS.
- Safe read paths now use the ADR 0163 retry taxonomy with the shared `/config/retry-policies.yaml` bundle.
- Non-idempotent webhook and proxied write paths remain single-shot until ADR 0165 idempotency keys are in place.
- Native `/v1/platform/*` endpoints read repo-synced catalogs copied into the runtime bundle.
- Error responses for repo-managed gateway endpoints use the canonical registry in `config/error-codes.yaml`.
- The public edge certificate for `api.lv3.org` is part of the shared `lv3-edge` certificate on `nginx-lv3`.
