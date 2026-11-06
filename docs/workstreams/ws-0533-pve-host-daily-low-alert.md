# WS-0533: Warn when the hypervisor's 24-hour free-space low gets close to the hold

## Status

Merged (PR 584, `054003541`) and applied live on 2026-10-26 at 23:02Z; receipt `2026-10-26-pve-host-daily-low-alert-monitoring-live-apply`. The repository version bump that carries the change is still the integration step, so `included_in_repo_version` stays null until then.

## Goal

The hypervisor root filesystem (`/dev/md3`) holds every guest disk of that host. CI admission is held under 14% free and `PveHostFilesystemLowHeadroom` warns at 15%, but the free fraction swings by several points within minutes: a daily state backup stages about 18 GiB for a quarter of an hour, and an application database log once grew by tens of GiB in a night. By the time the 15% warning has waited its five minutes, the hold is already on. The warning needs lead time and memory.

## Change

- `PveHostFilesystemDailyLowNarrow` in `config/prometheus/rules/pve-host-incident.yml`: a warning when the lowest free fraction of `/dev/md3` over the last 24 hours (5-minute grid) is under 16%, two points above the hold. It looks at the daily low, not the current value, so a dip that came close to the hold stays visible for a day after the filesystem has recovered, and it stays quiet on ordinary days.
- `tests/promtool/pve_host_free_space_rules_test.yml`: the alert stays quiet while every sample is above 16%, fires after a dip to 15%, still fires 23 hours later and clears after 25 hours; a dip to exactly 16% does not fire.
- `tests/test_pve_host_free_space_rules.py`: pins the alert's labels, the job and device selectors shared with the other host alerts, the thresholds the unit test assumes, and runs `promtool check` and the unit test when promtool is installed.

## Verification and rollback

- `promtool check rules`, `promtool test rules` and the two pytest files that read this rule file (`tests/test_adopted_prometheus_rules.py`, `tests/test_pve_host_free_space_rules.py`) pass.
- The expression was also run against the live Prometheus on 2026-10-25: it does not fire now (the 24 hour low is 18.6%). In the previous 72 hours the condition held for 23 hours, all of them the day after a dip to 13.4% on 2026-10-22, and over the previous seven days for 119 of 168 hours (the week of dips that ended on 2026-10-23); it has been quiet since.
- Roll back by removing the alert from the rule file; nothing else depends on it.

## Live apply

- Applied on 2026-10-26 at 23:02Z to the monitoring VM (`monitoring-lv3`) with a targeted Ansible play that installs `config/prometheus/rules/pve-host-incident.yml` with the `monitoring_vm` role's own parameters (root:prometheus, 0640), validates it with the VM's `promtool`, and reloads Prometheus with a SIGHUP, as the role's handler does. The play first checked that the source and the live file were the reviewed ones and kept the previous file as `pve-host-incident.yml.pre-daily-low-20261026T230155Z`.
- Why not `make live-apply-service service=grafana`: its vulnerability budget gate rejected (the monitoring host scan was 15.6 days old, limit 7 days) and its immutable guest replacement gate needs `ALLOW_IN_PLACE_MUTATION=true`; `make converge-monitoring` runs seven playbooks and cannot be narrowed to one file. The receipt records that path as partial.
- Result: the alert is loaded in group `pve_host_incident`, healthy and inactive (the 24-hour low is 18.87% against the 16% threshold); the reload succeeded without a restart; only that file and the new backup copy changed in `/etc/prometheus/rules`.
- Rollback: copy the `.pre-daily-low-` file back over `pve-host-incident.yml` and send SIGHUP to `0mcp-prometheus.service`.
- Still different from main on the VM, on purpose: `inventory.yml` and `fleet-loops.yml` (other workstreams' changes) and the mode of four rule files; a later converge ships them.

## Not in this change

An alert on the Fleet Graph write-ahead log size (`fleet_graph_store_wal_bytes`) was considered. That metric is scraped by the metrics hub's Prometheus, not by the one this repository's rules are loaded into, so a rule here would never fire. The metrics hub already alerts on it (`FleetGraphWalNotFolding` above 4 GiB and `FleetGraphWalVeryLarge` above 16 GiB, in its `prometheus/rules/graph-collector-alerts.yml`, since 2026-10-23).
