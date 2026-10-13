# Workstream ws-0521: Add private Prometheus host metrics for 0own

## Goal

Give the fleet monitoring VM direct, low-overhead CPU, memory, filesystem, and
load visibility for the new 0own Proxmox host, while keeping the exporter
reachable only over Tailscale. Restore QEMU guest-agent visibility for the
OpenObserve VM and watch its health before assigning more storage work.

## Scope

- Restart only VM630's unresponsive QEMU guest-agent service and verify Proxmox
  can query the running Debian guest.
- Install Debian's node exporter on the 0own Proxmox host and bind it to the
  host's Tailscale address on TCP 9100.
- Permit only monitoring-lv3 to scrape that host and add a Tailscale policy
  test for the allowed source/destination/port.
- Add the production-only 0own scrape job to the active Prometheus config with a
  narrow playbook. Preserve existing fleet jobs and `remote_write`; validate the
  config before SIGHUP and restore the automatic backup on any failure. Leave
  PostgreSQL on pve01 outside this change and avoid additional I/O.
- Keep a quiet read-only heartbeat for fleet capacity and service health.

## Preflight and rollback

The network-policy change allows only monitoring-lv3 (`203.0.113.4`) to
connect to 0own (`203.0.113.3:9100`) over Tailscale. The exporter is bound
only to the destination's Tailscale address. The scrape update touches only
monitoring-lv3's active Prometheus config, validates the prior and updated
config with `promtool`, and sends SIGHUP only when the file changes. It retains
an automatic backup and restores/reloads it if validation or target checks
fail. No service restart, PostgreSQL I/O, or OpenObserve app-container change
is part of this step.

## Validation

- Verify `qm agent 630 ping` and `qm agent 630 get-osinfo` after the guest-agent
  restart.
- Validate the Tailscale policy through the API before applying it, use an
  ETag precondition, and verify the live policy afterward.
- Verify Tailscale connectivity and fetch `node_load1` from the monitoring VM.
- Run the targeted role tests and Ansible syntax check. After merge, run
  `playbooks/services/prometheus-0own-node-exporter.yml` against only the
  monitoring VM, then verify `up{job="pve_0own_host_node_exporter_via_tailscale",monitored_host="proxmox-node"}` is `1` and `node_load1` has a sample.

## Live state

The OpenObserve guest-agent check was restored and all four 0own guests became
visible to the capacity report. The exporter is installed and responding over
the narrow Tailscale path. PRs #277, #278, #279, and #280 merged the guarded
playbook, its role invocation, template fix, and the monitoring VM's actual
`0mcp-prometheus.service` name. The playbook now verifies that unit is active
before it reads or edits the live config.

The first live run safely restored the prior config when the placeholder unit
name failed at reload. The corrected run, `ws0521-prometheus-apply-20261008r2`,
targeted only `monitoring-lv3`, validated the config, sent SIGHUP, and completed
with no task failures or service restart. Prometheus is ready and its active
config passes `promtool`. The 0own target
`up{job="pve_0own_host_node_exporter_via_tailscale",monitored_host="proxmox-node"}`
is `1`; a live `node_load1` sample was retained (10.23 at verification).

The first post-apply target snapshot had 249 active targets, 246 up, and 3
down. 0own was up; the 0docker target briefly returned a connection reset.
The final recheck had 249 active, 247 up, and 2 down. Both 0own and 0docker
were up, and the 0docker `node_uname_info` sample identified `0docker-builder`.
The remaining down targets were `10.10.10.60:9100` (no route) and
`10.10.10.10:9100` (timeout). The 0docker Tailscale listener is the existing
`woodpecker-exec-proxy@9100.socket`; it was left unchanged. PostgreSQL on
pve01 was not queried or changed.
