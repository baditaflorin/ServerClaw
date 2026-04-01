# Configure Typesense

## Purpose

Operate the private Typesense runtime that implements ADR 0277's structured
full-text search layer and keep the repo-managed `platform-services`
collection replayable from git.

## Repo Sources Of Truth

- `playbooks/typesense.yml`
- `playbooks/services/typesense.yml`
- `roles/typesense_runtime`
- `roles/api_gateway_runtime`
- `scripts/typesense_catalog_sync.py`
- `config/service-capability-catalog.json`
- `config/api-gateway-catalog.json`

## Preconditions

- OpenBao is already converged and the controller can reach the private
  OpenBao endpoint.
- The controller has the shared bootstrap SSH key at
  `.local/ssh/hetzner_llm_agents_ed25519`.
- `docker-runtime-lv3` and `proxmox_florin` are reachable through the standard
  Proxmox jump path.

## Converge

Focused converge:

```bash
make converge-typesense
```

Governed production live apply:

```bash
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=typesense env=production
```

The converge flow:

- publishes the private controller endpoint through the Proxmox host
  Tailscale TCP proxy
- generates and mirrors the controller-local Typesense API key into the
  OpenBao-backed runtime env contract
- deploys the Typesense runtime on `docker-runtime-lv3`
- refreshes the repo-managed `platform-services` collection through
  `scripts/typesense_catalog_sync.py`
- re-verifies the authenticated
  `/v1/platform/search/structured?q=...&collection=platform-services` route on
  the shared API gateway

## Verify

Run:

```bash
make syntax-check-typesense
TYPESENSE_API_KEY=$(cat .local/typesense/api-key.txt)
curl -fsS http://100.64.0.1:8016/health
curl -fsS -H "X-TYPESENSE-API-KEY: $TYPESENSE_API_KEY" \
  http://100.64.0.1:8016/collections/platform-services
LV3_TOKEN=$(cat .local/platform-context/api-token.txt)
curl -fsS -H "Authorization: Bearer $LV3_TOKEN" \
  'https://api.lv3.org/v1/platform/search/structured?q=api&collection=platform-services'
```

Expected results:

- `http://127.0.0.1:8108/health` returns `200` on `docker-runtime-lv3`
- `http://100.64.0.1:8016/collections/platform-services` returns `200` with
  a non-zero `num_documents` count when the repo-managed API key is presented
- the authenticated structured-search route returns
  `"backend": "typesense"` and at least one result for `q=api`

## Controller Artifacts

- `.local/typesense/api-key.txt`
- `receipts/image-scans/2026-03-30-typesense-runtime.json`
- `receipts/live-applies/`

## Recovery Notes

- Re-run `make converge-typesense` instead of hand-editing the runtime,
  collection schema, or Proxmox host proxy rules.
- If the controller-local API key is lost, delete
  `.local/typesense/api-key.txt` and replay the converge from git.
- The platform service catalog is derived state. After restoring the guest or
  the `typesense-data` volume, replay the Typesense converge and let the API
  gateway role repopulate `platform-services`.
