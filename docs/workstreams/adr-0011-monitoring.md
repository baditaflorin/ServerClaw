# Workstream ADR 0011: Monitoring Stack Rollout

- ADR: [ADR 0011](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md)
- Title: Monitoring VM and Grafana rollout
- Status: ready
- Branch: `codex/adr-0011-monitoring`
- Worktree: `../proxmox_florin_server-monitoring`
- Owner: unassigned
- Depends On: none
- Conflicts With: none
- Shared Surfaces: `monitoring-lv3`, `grafana.lv3.org`, Proxmox metrics export

## Scope

- converge the monitoring VM at `10.10.10.40`
- install Grafana and the chosen metric store
- wire Proxmox host metrics into the monitoring stack
- publish Grafana behind the intended ingress path

## Non-Goals

- Tailscale rollout
- backup policy
- replacing the current ingress model

## Expected Repo Surfaces

- `roles/` for monitoring automation
- `inventory/host_vars/proxmox_florin.yml`
- `docs/runbooks/`
- `docs/adr/0011-monitoring-vm-with-grafana-and-proxmox-metrics.md`

## Expected Live Surfaces

- VM `140`
- possibly VM `110` if Grafana is exposed via NGINX
- Proxmox metric export configuration

## Verification

- monitoring VM reachable on `10.10.10.40`
- Grafana reachable through the intended service path
- Proxmox host metrics visible in dashboards

## Merge Criteria

- automation is idempotent
- dashboards or provisioning steps are documented
- workstream status is updated in `workstreams.yaml`

## Notes For The Next Assistant

- keep monitoring isolated from Tailscale changes unless there is an explicit dependency
- do not update `platform_version` until the merged work is actually applied live from `main`
