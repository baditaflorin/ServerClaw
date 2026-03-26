# Workstream ADR 0152: Homepage for Unified Service Dashboard

- ADR: [ADR 0152](../adr/0152-homepage-for-unified-service-dashboard.md)
- Title: Repo-generated Homepage dashboard on docker-runtime-lv3 with authenticated publication at `home.lv3.org`
- Status: ready
- Branch: `codex/adr-0152-homepage-main`
- Worktree: `../proxmox_florin_server-homepage-integration`
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

- Repository implementation landed on the workstream branch and the focused Homepage validation suite passed on 2026-03-25.
- Homepage config generation and runtime verification succeeded on `docker-runtime-lv3`, including the generated `/api/services`, `/api/bookmarks`, and `/api/widgets` endpoints.
- Public rollout is still incomplete: on 2026-03-25 `home.lv3.org` did not resolve from `1.1.1.1`, and forcing `Host: home.lv3.org` to `65.108.75.123` returned the generic `LV3 Edge` default page instead of Homepage.
- The live apply is blocked by management-plane reachability from the controller: `65.108.75.123:22` times out, `100.118.189.95:22` refuses connections, and the remote build gateway through `docker-build-lv3` is unreachable.
- On 2026-03-26 the current controller public IP was `90.95.35.115`; the repo-managed Proxmox management allowlist was updated to include `90.95.35.115/32`, but the host was still unreachable from that controller so the change could not yet be applied live.

## Notes For The Next Assistant

- Keep Homepage config generation anchored to the canonical service and subdomain catalogs rather than ad hoc per-service files.
- Edge auth for `home.lv3.org` is shared infrastructure. Do not add a separate Homepage auth stack unless the broader portal-auth model changes.
- Resume from `../proxmox_florin_server-homepage-integration` on `codex/adr-0152-homepage-main`; local code changes for the runtime and edge roles are already present there.
- After management access is restored, finish the second `nginx-lv3` play in `playbooks/homepage.yml`, provision `home.lv3.org` DNS if still missing, verify the public endpoint, then update release and ADR/platform metadata from the current `origin/main` base.
