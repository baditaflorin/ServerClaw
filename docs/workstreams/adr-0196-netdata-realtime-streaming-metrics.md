# Workstream ADR 0196: Netdata Realtime Streaming Metrics

- ADR: [ADR 0196](../adr/0196-netdata-realtime-streaming-metrics.md)
- Title: Repo-managed Netdata parent and child streaming metrics with authenticated publication at `realtime.example.com`
- Status: implemented
- Implemented In Repo Version: 0.177.25
- Implemented In Platform Version: 0.130.32
- Implemented On: 2026-03-27
- Branch: `codex/ws-0196-main-merge-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0196-live-apply`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0071-agent-observation-loop`, `adr-0133-portal-authentication-by-default`
- Conflicts With: none
- Shared Surfaces: `roles/netdata_runtime`, `playbooks/realtime.yml`, `inventory/host_vars/proxmox-host.yml`, `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `docs/runbooks/`

## Scope

- add a repo-managed `netdata_runtime` role for the monitoring parent and child
  agents
- publish `realtime.example.com` through the shared authenticated NGINX edge
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

- `monitoring` serves the Netdata parent on `http://10.10.10.40:19999`
- `proxmox-host`, `nginx-edge`, `docker-runtime`, and `postgres`
  stream into the parent
- `realtime.example.com` redirects unauthenticated browsers to `/oauth2/sign_in`
- Prometheus scrapes the parent exporter on `monitoring`

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
- `realtime.example.com` resolves publicly, presents the shared edge certificate,
  and redirects unauthenticated browsers to `/oauth2/sign_in`
- Prometheus on `monitoring` now ingests consolidated Netdata metrics for
  the parent plus all expected streamed nodes
- Uptime Kuma bootstrap and ensure-monitors both succeeded with the generated
  realtime monitor contract from the separate worktree
- the latest-main replay root cause was fixed by explicitly loading
  `inventory/group_vars/platform.yml` in every realtime play, and the follow-up
  `make converge-realtime env=production` rerun restored the realtime edge vhost
  and confirmed the expected oauth2 redirect

## Mainline Integration

- merged to `main` in repository version `0.177.25`
- the canonical live-apply receipt is now tracked in
  `versions/stack.yaml.live_apply_evidence.latest_receipts.realtime`
