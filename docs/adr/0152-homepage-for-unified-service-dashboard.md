# ADR 0152: Homepage for Unified Service Dashboard

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.169.0
- Implemented In Platform Version: 0.130.19
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

The platform now has enough private and edge-published services that operators need a single browser-accessible entrypoint for discovery before they can do useful work. The canonical service inventory, URLs, and publication metadata already live in:

- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `inventory/host_vars/proxmox_florin.yml`
- `versions/stack.yaml`

Those sources are accurate, but they are still repository-first data structures. They are not the fastest way to answer "what is live, where does it run, and which URL should I open first?" during onboarding, routine operations, or break-glass recovery.

## Decision

We run Homepage on `docker-runtime-lv3` as the unified LV3 service dashboard and generate its repo-managed configuration directly from the canonical service and subdomain catalogs.

### Runtime shape

- service id: `homepage`
- runtime host: `docker-runtime-lv3`
- private listener: `http://10.10.10.20:3090`
- public URL: `https://home.lv3.org`
- publication model: shared `nginx_edge_publication` route with the existing Keycloak-backed oauth2-proxy gate
- image: `ghcr.io/gethomepage/homepage:v1.8.0@sha256:a543b3b044b2fa349dfe319c9e9b256c4eb5b4f6923361045aa468be4d2ba990`

### Config generation

`scripts/generate_homepage_config.py` is the canonical renderer for Homepage configuration. It reads:

- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `versions/stack.yaml`

and writes:

- `services.yaml`
- `bookmarks.yaml`
- `widgets.yaml`
- `settings.yaml`
- `custom.css`

The generated dashboard prefers public URLs when they exist, falls back to browser-usable private URLs when needed, groups services by the canonical capability category, and uses internal URLs for Homepage site-monitor checks so shared edge auth does not break status dots.

### Publication and auth boundary

Homepage does not own an application-level auth integration. It is protected at the shared edge in the same way as `ops.lv3.org`, `docs.lv3.org`, and `changelog.lv3.org`:

- `home.lv3.org` is declared with `auth_requirement: edge_oidc`
- `nginx_edge_publication` routes it through the existing oauth2-proxy
- the Homepage runtime stays simple and read-only

## Implementation Notes

- `playbooks/homepage.yml` converges both the Homepage runtime on `docker-runtime-lv3` and the `home.lv3.org` edge publication on `nginx-lv3`.
- `roles/homepage_runtime` regenerates Homepage config from repo state on every converge before restarting the container.
- The service is registered in the service, subdomain, health-probe, dependency, image, SLO, workflow, and data catalogs.
- Uptime Kuma now manages a `Homepage Public` monitor, and the monitoring stack consumes the new Homepage SLO target.

## Consequences

### Positive

- Operators now have a single repo-managed starting URL for service discovery.
- Dashboard content stays aligned with the canonical catalogs instead of a hand-maintained UI configuration.
- Homepage remains low-risk because auth and public publication stay in the existing shared edge path.

### Trade-offs

- Homepage adds one more runtime on `docker-runtime-lv3`.
- The dashboard is only as accurate as the canonical catalogs that feed it; missing catalog updates will produce missing dashboard entries.
- Homepage remains read-only by design, so operator actions still flow through the ops portal, CLI, or direct service UIs.

## Verification

Repository release `0.169.0` and live platform version `0.130.19` verified on 2026-03-26:

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_homepage_config.py tests/test_homepage_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_generate_platform_vars.py tests/test_subdomain_catalog.py tests/test_validate_service_catalog.py tests/test_uptime_contract.py tests/test_slo_tracking.py -q` passed with `39 passed`
- `make syntax-check-homepage` passed
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` passed
- `uv run --with pyyaml python scripts/validate_alert_rules.py` passed
- `make converge-homepage` completed successfully from `main`
- `curl -skI https://home.lv3.org` returned `HTTP/2 302` to `/oauth2/sign_in`
- `dig +short home.lv3.org @1.1.1.1` returned `65.108.75.123`

## Related ADRs

- ADR 0075: Service capability catalog
- ADR 0076: Subdomain governance
- ADR 0093: Interactive ops portal
- ADR 0123: Service uptime contracts and monitor-backed health
- ADR 0133: Portal authentication by default
