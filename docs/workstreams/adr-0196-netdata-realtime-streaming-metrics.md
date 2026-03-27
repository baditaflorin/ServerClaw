# Workstream ADR 0196: Netdata Realtime Streaming Metrics

- ADR: [ADR 0196](../adr/0196-netdata-realtime-streaming-metrics.md)
- Title: Repo-managed Netdata parent and child streaming metrics with authenticated publication at `realtime.lv3.org`
- Status: implemented
- Implemented In Repo Version: 0.177.12
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Branch: `codex/ws-0196-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0196-live-apply`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0071-agent-observation-loop`, `adr-0133-portal-authentication-by-default`
- Conflicts With: none
- Shared Surfaces: `roles/netdata_runtime`, `playbooks/realtime.yml`, `inventory/host_vars/proxmox_florin.yml`, `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `docs/runbooks/`

## Scope

- add a repo-managed `netdata_runtime` role for the monitoring parent and child
  agents
- publish `realtime.lv3.org` through the shared authenticated NGINX edge
- register the service in the catalog, health, SLO, dependency, and data
  contracts
- export the consolidated parent metrics to Prometheus
- add an observation-loop signal and operator CLI shortcut for the live metrics
  surface

## Non-Goals

- replacing Prometheus or Grafana as the retained metrics system of record
- publishing anonymous public metrics
- adding long-retention metric storage inside Netdata

## Expected Repo Surfaces

- `collections/ansible_collections/lv3/platform/roles/netdata_runtime/`
- `playbooks/realtime.yml`
- `playbooks/services/realtime.yml`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/health-probe-catalog.json`
- `docs/runbooks/configure-netdata.md`
- `docs/adr/0196-netdata-realtime-streaming-metrics.md`
- `docs/workstreams/adr-0196-netdata-realtime-streaming-metrics.md`

## Expected Live Surfaces

- `monitoring-lv3` serves the Netdata parent on `http://10.10.10.40:19999`
- `proxmox_florin`, `nginx-lv3`, `docker-runtime-lv3`, and `postgres-lv3`
  stream into the parent
- `realtime.lv3.org` redirects unauthenticated browsers to `/oauth2/sign_in`
- Prometheus scrapes the parent exporter on `monitoring-lv3`

## Verification

- Run focused pytest, syntax-check, data-model, health-probe, and alert-rule
  validation for the new realtime service surfaces
- Run the live DNS, edge, parent, child-streaming, Prometheus, and observation
  checks from `docs/runbooks/configure-netdata.md`

## Outcome

- the repo now carries the `netdata_runtime` role plus the realtime service,
  subdomain, health, SLO, dependency, and data catalog wiring for ADR 0196
- `make live-apply-service service=realtime env=production EXTRA_ARGS='-e bypass_promotion=true'`
  completed successfully from the separate worktree after fixing fresh-worktree
  portal generation, Debian 13 Netdata package bootstrap, and Prometheus scrape
  convergence in the realtime path
- `realtime.lv3.org` resolves publicly, presents the shared edge certificate,
  and redirects unauthenticated browsers to `/oauth2/sign_in`
- Prometheus on `monitoring-lv3` now ingests consolidated Netdata metrics for
  the parent plus all expected streamed nodes
- Uptime Kuma bootstrap and ensure-monitors both succeeded with the generated
  realtime monitor contract from the separate worktree

## Remaining For Merge To `main`

- update the protected integration files only during the merge step:
  `VERSION`, the release sections in `changelog.md`, the top-level `README.md`
  integrated status summary, and `versions/stack.yaml`
- add the realtime receipt mapping in `versions/stack.yaml.live_apply_evidence.latest_receipts`
  during the final mainline integration step
