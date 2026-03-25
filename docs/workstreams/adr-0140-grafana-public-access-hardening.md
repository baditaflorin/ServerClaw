# Workstream ADR 0140: Grafana Public Access Hardening

- ADR: [ADR 0140](../adr/0140-grafana-public-access-hardening.md)
- Title: Remove unauthenticated Grafana visibility and version disclosure from the public edge
- Status: live_applied
- Implemented In Repo Version: 0.124.1
- Live Applied In Platform Version: 0.130.1
- Implemented On: 2026-03-24
- Live Applied On: 2026-03-24
- Branch: `codex/adr-0140-grafana-hardening`
- Worktree: `.worktrees/adr-0140-grafana-hardening`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0056-keycloak-sso`, `adr-0109-public-status-page`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `roles/monitoring_vm/`, `roles/nginx_edge_publication/`, `docs/runbooks/`, `tests/`

## Scope

- add ADR 0140 to record the Grafana public-hardening decision and implementation state
- explicitly disable Grafana public dashboards, keep the recovery login form, and keep embedding disabled
- harden the NGINX publication for `grafana.lv3.org` so `/api/health` is blocked and version headers are stripped
- add repository verification that unauthenticated dashboard URLs redirect to login instead of rendering dashboard content
- document the operator verification path in the monitoring and edge-publication runbooks

## Non-Goals

- redesigning Grafana dashboards or changing alert logic
- replacing Grafana's Keycloak login flow with a different auth architecture
- publishing Grafana as a public status page

## Expected Repo Surfaces

- `inventory/host_vars/proxmox_florin.yml`
- `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`
- `roles/nginx_edge_publication/templates/lv3-edge.conf.j2`
- `roles/monitoring_vm/tasks/main.yml`
- `roles/monitoring_vm/tasks/verify.yml`
- `docs/runbooks/monitoring-stack.md`
- `docs/runbooks/configure-edge-publication.md`
- `tests/test_monitoring_vm_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_service_topology_filters.py`

## Expected Live Surfaces

- `https://grafana.lv3.org/d/lv3-platform-overview/lv3-platform-overview` redirects unauthenticated callers to `/login`
- `https://grafana.lv3.org/api/health` returns `404`
- the public login response does not expose `X-Grafana-Version` or `Via`
- local Grafana health and admin API checks on `monitoring-lv3` remain healthy

## Verification

- `uv run --with pytest --with pyyaml python -m pytest tests/test_monitoring_vm_role.py tests/test_nginx_edge_publication_role.py tests/test_service_topology_filters.py -q`
- `make syntax-check-monitoring`
- `curl -I https://grafana.lv3.org/d/lv3-platform-overview/lv3-platform-overview`
- `curl -i https://grafana.lv3.org/api/health`
- `curl -I https://grafana.lv3.org/login`

## Merge Criteria

- Grafana explicitly disables anonymous access and public dashboards in repo-managed config
- the public edge blocks external `/api/health` exposure
- repository verification proves dashboard URLs do not render for unauthenticated callers
