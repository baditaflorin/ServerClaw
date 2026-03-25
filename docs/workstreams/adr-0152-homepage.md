# Workstream ADR 0152: Homepage for Unified Service Dashboard

- ADR: [ADR 0152](../adr/0152-homepage-for-unified-service-dashboard.md)
- Title: Repo-generated Homepage dashboard on docker-runtime-lv3 with authenticated publication at `home.lv3.org`
- Status: live_applied
- Branch: `codex/adr-0152-homepage-dashboard`
- Worktree: `../proxmox_florin_server-homepage-dashboard`
- Owner: codex
- Depends On: `adr-0075-service-capability-catalog`, `adr-0076-subdomain-governance`, `adr-0093-interactive-ops-portal`, `adr-0133-portal-authentication-by-default`
- Conflicts With: none
- Shared Surfaces: `roles/homepage_runtime`, `playbooks/homepage.yml`, `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `inventory/host_vars/proxmox_florin.yml`, `docs/runbooks/`

## Scope

- add a repo-managed `homepage_runtime` role and `playbooks/homepage.yml`
- generate Homepage config from the canonical service and subdomain catalogs
- publish `home.lv3.org` through the shared NGINX edge with the existing Keycloak-backed oauth2-proxy gate
- register Homepage in the service, subdomain, health-probe, dependency, SLO, image, workflow, and data catalogs
- document operator converge and verification steps in `docs/runbooks/configure-homepage.md`

## Non-Goals

- direct mutation workflows from the Homepage UI
- service-specific OIDC inside Homepage itself
- replacing the ops portal as the primary action surface

## Expected Repo Surfaces

- `roles/homepage_runtime/`
- `playbooks/homepage.yml`
- `scripts/generate_homepage_config.py`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/health-probe-catalog.json`
- `docs/runbooks/configure-homepage.md`
- `docs/adr/0152-homepage-for-unified-service-dashboard.md`
- `docs/workstreams/adr-0152-homepage.md`

## Expected Live Surfaces

- `docker-runtime-lv3` serves Homepage on `http://10.10.10.20:3090`
- `home.lv3.org` is published through the shared authenticated edge
- Uptime Kuma manages the `Homepage Public` monitor
- the generated dashboard reflects the canonical service and subdomain catalogs

## Verification

- Run `uv run --with pytest --with pyyaml python -m pytest tests/test_homepage_config.py tests/test_homepage_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_subdomain_catalog.py tests/test_generate_platform_vars.py -q`
- Run `make syntax-check-homepage`
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- Run the private and public curl checks from `docs/runbooks/configure-homepage.md`

## Merge Criteria

- Homepage converges repeatably from repo-managed automation
- the public route is protected by the shared edge auth path
- Homepage config is generated from canonical repo data, not hand-maintained
- Uptime Kuma and SLO generation incorporate the new dashboard URL

## Outcome

- `make converge-homepage` completed successfully on 2026-03-25
- Homepage responded on `http://10.10.10.20:3090/` with the repo-managed dashboard title
- `home.lv3.org` published through the shared edge and redirected unauthenticated requests into oauth2-proxy as expected
- `make uptime-kuma-manage ACTION=ensure-monitors` added the `Homepage Public` monitor

## Notes For The Next Assistant

- Keep Homepage config generation anchored to the canonical service and subdomain catalogs rather than ad hoc per-service files.
- Edge auth for `home.lv3.org` is shared infrastructure. Do not add a separate Homepage auth stack unless the broader portal-auth model changes.
