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

If the controller cannot reach guests directly over Tailscale, use the Proxmox jump path:

```bash
ansible-playbook -i inventory/hosts.yml -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/api-gateway.yml
```

## Verify

From `docker-runtime-lv3`:

```bash
curl -sf http://127.0.0.1:8083/healthz
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8083/v1/health
```

Expected:

- `/healthz` returns `200`
- `/v1/health` returns `401` without a bearer token

From an operator workstation with a valid Keycloak token:

```bash
curl https://api.lv3.org/healthz
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/health
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/platform/services
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/platform/degradations
```

From `docker-runtime-lv3`, confirm the writable data volume now holds the gateway degradation state and any temporary NATS outbox:

```bash
sudo ls -l /opt/api-gateway/data
sudo test -f /opt/api-gateway/data/degradation-state.json && sudo cat /opt/api-gateway/data/degradation-state.json || true
sudo test -f /opt/api-gateway/data/nats-outbox.jsonl && sudo cat /opt/api-gateway/data/nats-outbox.jsonl || true
```

## Notes

- The gateway validates Keycloak JWTs directly against the realm JWKS.
- When Keycloak is unavailable but the JWKS cache is still valid, the gateway now stays in a declared degraded mode instead of failing authentication immediately.
- When NATS publication fails, the gateway now buffers request events in `/opt/api-gateway/data/nats-outbox.jsonl` and flushes them on recovery.
- Native `/v1/platform/*` endpoints read repo-synced catalogs copied into the runtime bundle.
- The public edge certificate for `api.lv3.org` is part of the shared `lv3-edge` certificate on `nginx-lv3`.
