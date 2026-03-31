# Configure Lago

This runbook covers the repo-managed Lago deployment introduced by
[ADR 0292](../adr/0292-lago-as-the-usage-metering-and-billing-api-layer.md).

## Scope

The Lago workflow converges:

- the shared PostgreSQL role and `lago` database on `postgres-lv3`
- the Lago API, front end, worker, clock, Redis, and PDF sidecar on
  `docker-runtime-lv3`
- the shared API-gateway billing adapter that exposes
  `billing.lv3.org/api/v1/events` and `billing.lv3.org/api/health`
- the protected `billing.lv3.org` browser surface on the shared NGINX edge
- the repo-managed smoke billable metric, plan, customer, subscription, and
  public-ingest verification path
- the controller-local Lago artifacts mirrored under `.local/lago/`

## Current Live Contract

The current implementation uses these boundaries:

- the Lago browser UI and operator management surface stay behind the shared
  oauth2-proxy and Keycloak edge-auth flow
- `billing.lv3.org/api/health` remains intentionally public for probes
- `billing.lv3.org/api/v1/events` is intentionally public, but only through
  the API-gateway adapter that enforces producer bearer tokens plus
  repo-managed metric and subscription scope
- rejected or malformed billing payloads are published to
  `billing.events.rejected`
- the current runtime uses controller-local and guest-local file mirrors under
  `.local/lago/` and `/etc/lv3/lago/`; it does not yet rely on OpenBao-backed
  compose secret injection

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- Hetzner DNS API credentials are available when the edge certificate or DNS
  records need expansion
- the shared API gateway, NGINX edge, and PostgreSQL VM are already healthy

## Converge

On `main`, run:

```bash
HETZNER_DNS_API_TOKEN=... make live-apply-service service=lago env=production
```

This is the authoritative exact-main replay path because
`make live-apply-service` is what updates the canonical release and platform
truth surfaces.

On a successful live apply, the wrapper now also triggers the governed Restic
live-apply backup flow through the repo-managed Python environment. Treat the
run as incomplete unless the final JSON summary reports `status: ok`.

On a non-`main` workstream branch where protected release files must remain
untouched, prefer the service-scoped converge target:

```bash
HETZNER_DNS_API_TOKEN=... make converge-lago env=production
```

That entrypoint keeps the protected release files untouched and still refreshes
the shared edge-generated portal artifacts during `make preflight`.

Because `api_gateway_runtime` and `nginx_edge_publication` are shared live
surfaces, branch-local converges are best treated as pre-integration evidence.
If the branch-local replay reaches the shared billing edge but final public
verification diverges from the branch state, merge to the latest `main` and
repeat the exact-main replay before recording implementation truth or platform
version changes.

## Generated Local Artifacts

The workflow maintains controller-local artifacts under `.local/lago/`:

- `database-password.txt`
- `redis-password.txt`
- `secret-key-base.txt`
- `rsa-private-key.pem`
- `encryption-primary-key.txt`
- `encryption-deterministic-key.txt`
- `encryption-key-derivation-salt.txt`
- `bootstrap-user-password.txt`
- `org-api-key.txt`
- `smoke-producer-token.txt`
- `producer-catalog.json`

## Verification

Repository and syntax checks:

```bash
python3 scripts/validate_service_completeness.py --service lago
uv run --with pytest python -m pytest tests/test_api_gateway.py tests/test_api_gateway_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_generate_platform_vars.py tests/test_lago_playbook.py tests/test_lago_runtime_role.py
uv run --with pyyaml python scripts/generate_platform_vars.py --check
uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py validate
./scripts/validate_repo.sh agent-standards health-probes
make syntax-check-lago
```

Runtime verification:

```bash
curl -fsS https://billing.lv3.org/api/health
curl -I https://billing.lv3.org/
curl -fsS -X POST \
  -H "Authorization: Bearer $(tr -d '\n' < .local/lago/smoke-producer-token.txt)" \
  -H "Content-Type: application/json" \
  --data '{"event":{"transaction_id":"00000000-0000-4000-8000-000000000001","external_subscription_id":"lv3-billing-smoke-subscription","code":"api_calls"}}' \
  https://billing.lv3.org/api/v1/events
```

The converge playbook also verifies local health on `docker-runtime-lv3` and
checks current usage for the seeded smoke customer through the local Lago API.

## Operational Notes

- Update `.local/lago/producer-catalog.json` only through repo-managed defaults;
  the API gateway treats that file as the authoritative producer scope map.
- The browser UI is intentionally edge-authenticated rather than app-native
  OIDC. If anonymous browser access reaches `/`, treat that as a rollback-level
  defect.
- The public ingest endpoint is intentionally narrow. Producers should never
  talk directly to the private Lago API port on `10.10.10.20:8099`.
- Because the current secret path is controller-local plus guest-local file
  mirroring, treat `.local/lago/` as sensitive material and keep it out of git,
  screenshots, and ad hoc shell transcripts.
