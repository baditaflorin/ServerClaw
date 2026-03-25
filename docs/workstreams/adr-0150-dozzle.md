# Workstream ADR 0150: Dozzle for Real-Time Container Log Access

- ADR: [ADR 0150](../adr/0150-dozzle-for-real-time-container-log-access.md)
- Title: Real-time container log access through a repo-managed Dozzle hub and per-host agents
- Status: blocked
- Branch: `codex/live-apply-0150`
- Worktree: `.worktrees/live-apply-0150`
- Owner: codex
- Depends On: `adr-0023-docker-runtime`, `adr-0052-loki-logs`, `adr-0133-portal-auth-by-default`
- Conflicts With: none
- Shared Surfaces: `roles/dozzle_runtime`, `roles/nginx_edge_publication`, `inventory/host_vars/proxmox_florin.yml`, `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `config/api-gateway-catalog.json`

## Scope

- add a repo-managed `dozzle_runtime` role that runs a Dozzle hub on `docker-runtime-lv3`
- run Dozzle agents on `docker-runtime-lv3`, `docker-build-lv3`, and `monitoring-lv3`
- publish `logs.lv3.org` through the shared NGINX edge with the existing oauth2-proxy and Keycloak gate
- wire the service through image, workflow, command, health, dependency, SLO, data, alerting, and subdomain catalogs
- document the converge and verification path in `docs/runbooks/configure-dozzle.md`

## Non-Goals

- replacing Loki for long-term log storage or search
- enabling Dozzle container actions or shell access
- adding a new dedicated Keycloak client for Dozzle beyond the shared edge auth flow

## Expected Repo Surfaces

- `roles/dozzle_runtime/`
- `playbooks/dozzle.yml`
- `playbooks/services/dozzle.yml`
- `config/image-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/api-gateway-catalog.json`
- `config/subdomain-catalog.json`
- `docs/runbooks/configure-dozzle.md`
- `docs/adr/0150-dozzle-for-real-time-container-log-access.md`
- `docs/workstreams/adr-0150-dozzle.md`

## Expected Live Surfaces

- `docker-runtime-lv3` serves the Dozzle hub on `http://127.0.0.1:8089/healthcheck`
- `docker-runtime-lv3`, `docker-build-lv3`, and `monitoring-lv3` each serve a Dozzle agent on `:7007`
- `sudo docker exec dozzle /dozzle agent-test 10.10.10.30:7007` succeeds on `docker-runtime-lv3`
- `https://logs.lv3.org/` redirects unauthenticated browsers to `/oauth2/sign_in`

## Verification

- Run `uv run --with pytest python -m pytest tests/test_dozzle_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_validate_portal_auth.py tests/test_subdomain_exposure_audit.py -q`
- Run `make syntax-check-dozzle`
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- Run the live hub, agent, and edge checks from `docs/runbooks/configure-dozzle.md`

## Merge Criteria

- the Dozzle hub and per-host agents converge repeatably from the repo
- `logs.lv3.org` is published on the shared edge with oauth2-proxy protection
- the hub can reach the local and remote agents without ad hoc firewall changes
- the runtime image is digest-pinned and scanned before the live apply evidence is recorded

## Outcome

- the repo-managed Dozzle hub, agent, edge, catalog, alerting, and runbook implementation is complete in this worktree
- `uv run --with pytest python -m pytest tests/test_dozzle_runtime_role.py tests/test_nginx_edge_publication_role.py tests/test_validate_portal_auth.py tests/test_subdomain_exposure_audit.py -q` passed with `25 passed`
- `make syntax-check-dozzle`, `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`, `uvx --from ansible-lint ansible-lint playbooks/dozzle.yml collections/ansible_collections/lv3/platform/playbooks/dozzle.yml roles/dozzle_runtime collections/ansible_collections/lv3/platform/roles/dozzle_runtime`, `./scripts/validate_repo.sh health-probes`, and `./scripts/validate_repo.sh alert-rules` all passed
- live apply is blocked from this session because SSH to `100.118.189.95` and `65.108.75.123` failed and `make check-build-server` reported `build server ops@10.10.10.30 is unreachable`

## Notes For The Next Assistant

- Keep the edge streaming toggle in `nginx_edge_publication` when changing `logs.lv3.org`; Dozzle log streaming is sensitive to proxy buffering.
- Do not enable Dozzle actions or shell access without a separate ADR and a review of the Docker socket exposure boundary.
- Resume with a reachable operator path, then run the live hub, agent, and edge verification steps from `docs/runbooks/configure-dozzle.md` before changing ADR 0150 to `Implemented` or `Live Applied`.
