# Workstream ADR 0109: Public Status Page

- ADR: [ADR 0109](../adr/0109-public-status-page.md)
- Title: Public `status.example.com` backed by Uptime Kuma with maintenance-window publication and independent Uptime Robot monitoring
- Status: merged
- Branch: `codex/adr-0109-implementation`
- Worktree: `.worktrees/adr-0109`
- Owner: codex
- Depends On: `adr-0015-dns-subdomains`, `adr-0021-nginx-edge`, `adr-0027-uptime-kuma`, `adr-0076-subdomain-governance`, `adr-0080-maintenance-window`, `adr-0096-slo-tracking`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `scripts/maintenance_window_tool.py`, `scripts/uptime_kuma_tool.py`, `scripts/uptime_robot_tool.py`, nginx edge config, `config/subdomain-catalog.json`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`

## Scope

- add the public `status.example.com` hostname to the canonical service topology and subdomain catalog
- publish the Uptime Kuma status page slug `lv3-platform` through the shared NGINX edge
- extend `scripts/uptime_kuma_tool.py` to reconcile the status page and inspect maintenances
- extend `scripts/maintenance_window_tool.py` to sync public status-page maintenances on open and close
- add `scripts/uptime_robot_tool.py` plus canonical external-monitor configuration for independent checks
- add controller-local secret inventory and governed workflow or command metadata for the Uptime Robot wrapper
- add health-probe and service-catalog contracts for the public status page
- add a status-page SLO catalog stub for later ADR 0096 rule generation
- document the operational procedure in `docs/runbooks/public-status-page.md`

## Non-Goals

- applying the status page live from this repo change
- implementing the full ADR 0096 SLO rule generator
- implementing the full ADR 0097 alert-routing stack
- custom frontend work beyond Uptime Kuma's built-in status-page surface

## Expected Repo Surfaces

- `config/uptime-kuma/status-page.json`
- `config/uptime-robot/public-status-monitoring.json`
- `config/slo-catalog.json`
- `scripts/uptime_kuma_tool.py`
- `scripts/uptime_robot_tool.py`
- `scripts/maintenance_window_tool.py`
- `config/subdomain-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `inventory/host_vars/proxmox-host.yml`
- `docs/runbooks/public-status-page.md`

## Expected Live Surfaces

- `https://status.example.com` is publicly reachable without authentication once applied from `main`
- the Uptime Kuma public page shows the repo-managed public monitor groups
- opening a maintenance window creates the matching public maintenance entry in Uptime Kuma when the admin session is available
- Uptime Robot reports the three external public monitors defined in the repo config

## Verification

- `make generate-platform-vars`
- `uvx --from pyyaml python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/service_catalog.py --validate`
- `uvx --from pytest --with pyyaml --with nats-py --with jsonschema python -m pytest tests/test_maintenance_window_tool.py tests/test_subdomain_catalog.py tests/test_nginx_edge_publication_role.py tests/test_uptime_robot_tool.py -q`

## Merge Criteria

- repo validation passes with the new `status_page` service surface
- the Uptime Kuma wrapper can reconcile the public status page from repo config
- the Uptime Robot wrapper can reconcile the independent contacts and monitors from repo config
- ADR 0109 is marked implemented in-repo and the workstream is marked merged
