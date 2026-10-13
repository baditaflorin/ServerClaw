# Workstream ws-0522: Codify the 2026-10-11 live monitoring changes

## Goal

A full `playbooks/services/grafana.yml` converge re-renders
`/etc/prometheus/prometheus.yml` and `/etc/alertmanager/alertmanager.yml` from
the role templates. The last render (2026-10-11 03:41 UTC) dropped the node,
Proxmox, public-edge, cadvisor, and OpenObserve `remote_write` entries because
they had only ever been added by hand. Later the same day the stale probe jobs
were removed, Scanopy service discovery was added, and Alertmanager was moved to
ntfy-only routing, again by hand. This workstream puts all of that into git so
the next converge reproduces the live state instead of erasing it.

## Scope

- `prometheus.yml.j2` is data-driven: catalog probe jobs are restricted by an
  allow-list, placeholder and retired-subnet targets are dropped at relabel
  time, the fleet exporters, the public-edge job, and `remote_write` come from
  `inventory/host_vars/monitoring.yml`, and inventory-derived targets come only
  from the Scanopy file_sd jobs.
- The Scanopy generator, its timer, the inventory rules, and the Watchdog rule
  are installed by the `monitoring_vm` role.
- `alertmanager_runtime` renders ntfy-only routing and installs a
  `root:prometheus 0640` password file.
- Prometheus and Alertmanager configs are validated (`promtool`, `amtool`)
  before they replace the live files and are reloaded, not restarted.

- The `nginx` guest keeps the monitoring-only tcp 9100 firewall rule
  (`network_policy.guests.nginx`, rendered by `linux_guest_firewall`).
- `docs/runbooks/tailscale-metrics-grants.md` records the 2026-10-12 tailnet
  policy additions and the exporter listener changes on hosts outside this repo,
  and how the tailnet policy is now managed as code (`config/tailscale/`,
  `scripts/tailscale_policy_sync.py`; plan/apply is manual from CT108).

## Out of scope

- The incident-control metric drop-ins on the hypervisor belong to the
  `proxmox-incident-control` repository.
- ntfy users and topic ACLs (runtime database state), the Scanopy server, the
  `promq` helper, `public-critical-targets.yml`, and the older hand-maintained
  rule files are not managed by this repo yet.
- The ntfy `base-url` typo comes from the operator-local `.local/identity.yml`.

## Validation

Offline Jinja rendering of the templates compared against the live files,
`promtool check config` and `amtool check-config` run against the rendered
output on the monitoring host over stdin (no file written), and the repository
tests in `tests/test_monitoring_prometheus_codification.py`. See
`docs/runbooks/scanopy-service-discovery.md` for apply, verification, and
rollback.

## Live state

All changes are already live on the monitoring VM. After merge, converge the
monitoring host in check mode first and confirm the diff matches the runbook.
