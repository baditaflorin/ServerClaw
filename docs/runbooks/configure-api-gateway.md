# Configure API Gateway

## Purpose

Converge the repo-managed unified platform API gateway on `docker-runtime-lv3` and publish it on `api.lv3.org`.

## Entry Points

- Playbook: `playbooks/api-gateway.yml`
- Service wrapper: `playbooks/services/api-gateway.yml`
- Health probe id: `api_gateway`
- Catalog: `config/api-gateway-catalog.json`

## Local Validation

```bash
python3 scripts/api_gateway_catalog.py --validate
uv run --with pytest --with fastapi==0.116.1 --with httpx==0.28.1 --with uvicorn==0.35.0 --with pyyaml==6.0.2 --with cryptography==45.0.6 pytest tests/test_api_gateway.py tests/test_api_gateway_catalog.py
```

## Converge

```bash
ansible-playbook -i inventory/hosts.yml playbooks/api-gateway.yml
```

## Verify

From `docker-runtime-lv3`:

```bash
curl -sf http://127.0.0.1:8080/healthz
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/v1/health
```

Expected:

- `/healthz` returns `200`
- `/v1/health` returns `401` without a bearer token

From an operator workstation with a valid Keycloak token:

```bash
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/health
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/platform/services
```

## Notes

- The gateway validates Keycloak JWTs directly against the realm JWKS.
- Native `/v1/platform/*` endpoints read repo-synced catalogs copied into the runtime bundle.
- Public publication is ready in repo automation; live DNS and edge truth only become active after apply from `main`.
