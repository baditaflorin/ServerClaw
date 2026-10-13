# Scanopy Service Discovery And Monitoring Config

This runbook describes how Prometheus on the monitoring VM gets its
inventory-derived scrape targets from Scanopy, what the `monitoring_vm` and
`alertmanager_runtime` roles now render, and how to roll the change back.

## Why this exists

The monitoring VM used to scrape 120 hard-coded per-service blackbox probes
rendered from `config/health-probe-catalog.json`. Most of them pointed at
`127.0.0.1`, retired `10.10.10.x` guests, or `example.com` placeholders and
could never succeed. The live fleet exporters and the OpenObserve
`remote_write` block were added by hand and were not in the role template, so
every full monitoring converge silently erased them.

The role template is now data-driven and carries everything that must survive a
converge. Targets that can be discovered are not listed in git at all.

## Flow

```
Scanopy API (inventory)  ->  scanopy_sd.py  ->  /etc/prometheus/file_sd/scanopy-node.json
   (hosts, services,        (systemd timer,      /etc/prometheus/file_sd/scanopy-blackbox.json
    daemons, subnets)        every 5 minutes)    /var/lib/prometheus/node-exporter/scanopy_sd.prom
                                                          |
Prometheus jobs `node_exporter` and `scanopy-blackbox` read the file_sd files (refresh 1m);
rules in `config/prometheus/rules/inventory.yml` alert on staleness, shrinkage and missing exporters.
```

## What is managed where

| Surface | Source in git | Rendered by | Notes |
|---|---|---|---|
| `/etc/prometheus/prometheus.yml` | `roles/monitoring_vm/templates/prometheus.yml.j2` + `inventory/host_vars/monitoring.yml` | `monitoring_vm` (`tracing.yml`) | Validated with `promtool check config` before it replaces the live file; applied with SIGHUP (reload), not a restart. |
| Static fleet exporters, cadvisor, public-edge job | `monitoring_prometheus_extra_scrape_jobs`, `monitoring_prometheus_public_edge_targets_file` | `monitoring_vm` | Only exporters Scanopy does not publish. |
| OpenObserve `remote_write` | `monitoring_prometheus_remote_write_targets` | `monitoring_vm` | Password is never in git: `password_file` points at a systemd credential. |
| Prometheus credential drop-in | `monitoring_prometheus_remote_write_credentials` | `monitoring_vm` | `LoadCredentialEncrypted=` line only; the encrypted blob must already exist on the host and the role fails closed if it does not. |
| `scanopy_sd.py`, README, `extra-endpoints.json` | `roles/monitoring_vm/files/scanopy-sd/`, `monitoring_scanopy_sd_extra_endpoints` | `monitoring_vm` (`scanopy_sd.yml`) | The script is byte-identical to the version running since 2026-10-11. |
| `scanopy-sd.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-sd.*.j2` | `monitoring_vm` | Timer is enabled, never restarted by a converge. |
| `/etc/scanopy-sd/api-key` | controller-local `monitoring_scanopy_sd_api_key_local_file` | `monitoring_vm` | root `0600`. See "Secrets". |
| `scanopy_retag.py`, README | `roles/monitoring_vm/files/scanopy-retag/` | `monitoring_vm` (`scanopy_retag.yml`) | Tags Docker bridge subnets in Scanopy. See "Docker bridge subnet tagging". |
| `scanopy-retag.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-retag.*.j2` | `monitoring_vm` | 15-minute timer; enabled, never restarted by a converge. |
| `/etc/scanopy-retag/api-key` | controller-local `monitoring_scanopy_retag_api_key_local_file` | `monitoring_vm` | root `0600`. See "Secrets". |
| `scanopy_discover.py`, `schedule.json`, README | `roles/monitoring_vm/files/scanopy-discover/`, `monitoring_scanopy_discover_schedule` | `monitoring_vm` (`scanopy_discover.yml`) | Starts the daily Docker VM discoveries through the API. See "External discovery trigger". |
| `scanopy-discover.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-discover.*.j2` | `monitoring_vm` | Timer runs every 15 minutes (minute 02/17/32/47); enabled, never restarted by a converge. Reuses `/etc/scanopy-retag/api-key`. |
| `rules/inventory.yml`, `rules/zz-alertmanager-watchdog.yml` | `config/prometheus/rules/` | `monitoring_vm` | Reload only. `inventory.yml` also carries the `scanopy_retag` and `scanopy_discover` alert groups. |
| `/etc/alertmanager/alertmanager.yml` | `config/alertmanager/alertmanager.yml` | `alertmanager_runtime` | ntfy-only routing, validated with `amtool check-config`, applied with a reload. |
| `/etc/alertmanager/ntfy-password` | controller-local `alertmanager_runtime_ntfy_password_local_file` | `alertmanager_runtime` | root:prometheus `0640` (Alertmanager runs as `prometheus`). |

Not managed by this repo (see "Out of scope"): the ntfy users and topic ACLs
themselves, `/etc/prometheus/file_sd/public-critical-targets.yml`, the older
hand-maintained rule files, the Scanopy server, and the `promq` helper.

## Secrets

Nothing secret is committed.

- Scanopy API key: put the key in the controller-local file named by
  `monitoring_scanopy_sd_api_key_local_file`
  (default `{{ repo_shared_local_root }}/scanopy/api-key.txt`). The role copies
  it to `/etc/scanopy-sd/api-key` (root `0600`, `no_log`). The key is the vault
  secret `scanopy-inventory-reader-api-key` (read-only, shared with fleet-runner).
  If the controller-local file is missing or empty, the role requires a non-empty
  key that is already on the host and only enforces its owner and mode, so a
  working host key is never replaced by an empty value.
- Scanopy retag API key: put a key that is allowed to assign tags (Member or
  higher) in the controller-local file named by
  `monitoring_scanopy_retag_api_key_local_file`
  (default `{{ repo_shared_local_root }}/scanopy/retag-api-key.txt`). It is
  deliberately a different file from the Viewer key above: the Viewer key cannot
  write. Prefer a dedicated Member key over an Admin key. The role copies it to
  `/etc/scanopy-retag/api-key` (root `0600`, `no_log`) with the same
  never-replace-with-empty behaviour as the discovery key. Scanopy API keys
  cannot create other keys, so a new key has to be created by a signed-in user in
  Scanopy.
  The discovery trigger below reuses this same key (it needs the permission to
  start discovery sessions) and never installs or replaces a key itself; enable the
  retag tasks first.
- ntfy password: the ntfy user `alertmanager-notify` is a runtime user created
  with the ntfy CLI. Put its password in the controller-local file named by
  `alertmanager_runtime_ntfy_password_local_file`
  (production sets `{{ repo_shared_local_root }}/ntfy/alertmanager-notify-password.txt`
  in `inventory/host_vars/monitoring.yml`; the role default is the provisioned
  `alertmanager` user's file). Converge fails before changing anything when the
  file is missing. Make sure the file holds the password of the user named by
  `alertmanager_runtime_ntfy_username`: the converge overwrites
  `/etc/alertmanager/ntfy-password`.
- OpenObserve ingest password: stored as the host credential
  `/etc/credstore.encrypted/openobserve_password`
  (`systemd-creds encrypt`). Prometheus reads it from
  `/run/credentials/<unit>/openobserve_password`.

## Apply

Run the standard monitoring converge for the monitoring host. Preview first:

```bash
python3 scripts/ansible_scope_runner.py plan --playbook playbooks/services/grafana.yml --env production
```

Expected effect on the live monitoring VM, which already holds these changes:

- `prometheus.yml`: adds the three restored jobs (`pve_0docker_via_tailscale`,
  `cadvisor-runtime-general-lv3`, `public-edge-critical`) and `remote_write`; the
  Scanopy jobs are unchanged. Prometheus is reloaded with SIGHUP, not restarted.
- Scanopy units, script, rules: no change except the rendered
  `extra-endpoints.json` formatting.
- Alertmanager: `alertmanager.yml` is equivalent to the live file, so a reload
  is a no-op for routing. `/etc/alertmanager/ntfy-password` is rewritten from
  the controller-local file.
- A one-time Prometheus restart happens only if the unit file or the credential
  drop-in differs from what is on the host.

Verify:

```bash
ssh 0mcp_monitoring 'curl -fsS http://127.0.0.1:9090/-/ready'
ssh 0mcp_monitoring 'systemctl list-timers scanopy-sd.timer --no-pager'
ssh 0mcp_monitoring 'curl -fsS "http://127.0.0.1:9090/api/v1/targets?state=active" | python3 -c "import sys,json,collections;d=json.load(sys.stdin)[\"data\"][\"activeTargets\"];print(collections.Counter(t[\"scrapePool\"] for t in d))"'
ssh 0mcp_monitoring 'curl -fsS http://127.0.0.1:9093/-/ready'
```

The Prometheus API on the VM needs the query credential; use the repo's usual
authenticated query helper if the unauthenticated call is rejected.

## Behaviour of the generator

- A failed pull or a missing key keeps the last-good file_sd files and does not
  advance `scanopy_sd_last_success_timestamp_seconds`; `ScanopySDStale` fires
  after 30 minutes.
- If the inventory or a target class shrinks by more than 20 percent, the old
  files are kept and `scanopy_sd_guard_tripped=1` (`TargetCountDrop`). Accept a
  real shrink with `touch /var/lib/scanopy-sd/accept-shrink` on the VM; the next
  run consumes it.
- Only endpoints connectable from the monitoring VM are published, and each
  node_exporter identity is verified against `node_uname_info`. The reported
  nodename must equal an inventory name, or the first DNS label of one (the
  inventory name `scrapetheworld.org` runs a machine that reports
  `scrapetheworld`) provided that label is unique among inventory hosts. An
  ambiguous label is never accepted (`reason=identity_mismatch`). For anything
  else, put an explicit map in `/opt/scanopy-sd/node-aliases.json`:
  `{"inventory name": ["nodename"]}` (optional, not managed by the role).

## Docker bridge subnet tagging (scanopy-retag)

Discovery on a Docker host records every compose and bridge network as a Scanopy
subnet (hundreds on a busy host), which makes the topology view unreadable. The
topology can hide subnets by tag, so every subnet of type `DockerBridge` carries
the tag `docker-bridge`, and the topology option
`local.tag_filter.hidden_subnet_tag_ids` lists that tag's id.

Discovery creates new Docker networks untagged, so `scanopy-retag` runs every
15 minutes on the monitoring VM and tags any `DockerBridge` subnet that lacks the
tag. It only adds the tag: it never removes tags, never touches other subnet
types, and never deletes anything. A run fails (and the alert below fires)
instead of acting when the tag is missing or ambiguous, when the key is missing
or empty, or when more than `RETAG_MAX_PER_RUN` (500) subnets would be tagged at
once.

Prerequisites that live in Scanopy, not in git (create them once, in this order):

1. A tag named `docker-bridge`.
2. That tag added to the topology's hidden subnet tags
   (`options.local.tag_filter.hidden_subnet_tag_ids`).
3. A first tagging run (the timer does it; or run the job by hand).

Metrics (node_exporter textfile `scanopy_retag.prom`):
`scanopy_retag_last_attempt_success`, `scanopy_retag_last_success_timestamp_seconds`,
`scanopy_retag_docker_bridge_subnets`, `scanopy_retag_untagged_found`,
`scanopy_retag_tagged_this_run`. Alerts (`config/prometheus/rules/inventory.yml`):
`ScanopyRetagStale` (no successful run for 1h) and `ScanopyRetagMetricsAbsent`
(metrics missing for 30m).

Manual run on the monitoring VM:

```bash
sudo python3 /opt/scanopy-retag/scanopy_retag.py --dry-run   # report only
sudo systemctl start scanopy-retag.service && journalctl -u scanopy-retag -n 20
```

Roll back with `sudo systemctl disable --now scanopy-retag.timer` or
`monitoring_scanopy_retag_enabled: false` and a converge (installed files stay on
disk). Tags that were already applied stay; to show the Docker networks again,
empty `hidden_subnet_tag_ids` in the topology options.

## External discovery trigger (scanopy-discover)

Scanopy has its own scheduler (the `Scheduled` discovery definitions), but it does
not fire reliably here: in five days of server logs it fired once, for a schedule
that had just been saved. Schedules that were already stored, including the
weekly Sunday ones, never ran, and the server restart before that Sunday appears
to drop them. Treat Scanopy's scheduler as unreliable and drive the daily
discovery from outside.

`scanopy-discover` runs from a systemd timer on the monitoring VM every 15 minutes
(minute 02/17/32/47, just after the quarter-hour slots). `schedule.json`, rendered
from `monitoring_scanopy_discover_schedule`, maps each Scanopy daemon name to a
daily UTC slot. For every daemon whose slot has passed and whose discovery has not
run since that slot, the job calls `POST /api/v1/discovery/start-session` for its
`Scheduled` definition. That is the only call it makes that changes anything: it
creates, edits and deletes nothing in Scanopy.

- A discovery that already ran since its slot is skipped (including when Scanopy's
  own scheduler ran it), so scans are not doubled. HTTP 409 (a session is already
  running) is a skip, not an error.
- Catch-up window 3h (`DISCOVER_CATCHUP_HOURS`): a slot missed for longer waits for
  the next day instead of causing a burst of daytime scans. `ScanopyDiscoveryOverdue`
  reports that case.
- At most one session is started per run (`DISCOVER_MAX_STARTS_PER_RUN`). Slots are
  distinct quarter hours, and the large Docker host has a 45-minute window to itself.
- A run fails (exit 1, `scanopy_discover_last_attempt_success 0`) on a missing or
  empty key or schedule, an unknown daemon name, or a daemon without a `Scheduled`
  definition. The other targets still run.

The schedule covers the 16 Docker VM daemons (01:00 to 05:15 UTC) and the four Proxmox hypervisor daemons
(`pve-0docker`, `pve-0mcp`, `pve-0own`, `pve-pve01`, 05:30 to 06:15 UTC) so the Proxmox VE inventory stays fresh.

To add or move a host, edit `monitoring_scanopy_discover_schedule` in
`inventory/host_vars/monitoring.yml` (keep slots on distinct quarter hours) and
converge. The host's daemon must already have a `Scheduled` discovery definition in
Scanopy; the job does not create one.

Metrics (textfile `scanopy_discover.prom`): `scanopy_discover_last_attempt_success`,
`scanopy_discover_last_success_timestamp_seconds`, `scanopy_discover_targets`,
`scanopy_discover_due`, `scanopy_discover_started_this_run`, `scanopy_discover_errors`,
`scanopy_discover_oldest_last_run_age_seconds`. Alerts: `ScanopyDiscoverStale` (no
clean run for 1h), `ScanopyDiscoverMetricsAbsent` (metrics missing for 30m) and
`ScanopyDiscoveryOverdue` (some host's last run older than 36h). A host that was
last scanned days ago will trip the overdue alert until its first slot has run.

On the monitoring VM:

```bash
sudo python3 /opt/scanopy-discover/scanopy_discover.py --dry-run   # what is due
sudo systemctl start scanopy-discover.service && journalctl -u scanopy-discover -n 20
```

Roll back with `sudo systemctl disable --now scanopy-discover.timer` or
`monitoring_scanopy_discover_enabled: false` and a converge (installed files stay on
disk). Discovery then only runs when someone starts it by hand or when Scanopy's own
scheduler happens to fire.

### Scanopy daemons (installed by hand, not managed by a role)

Every guest and hypervisor runs a Scanopy daemon (DaemonPoll mode, polls the server every 30 s; the server is on the 0docker
hypervisor). There is no role for them, so this is the layout to restore or extend:

- Unit `scanopy-daemon.service`, `ExecStart=/usr/local/bin/scanopy-daemon --config-dir /etc/scanopy/daemon/scanopy-daemon
  --log-file /var/log/scanopy/scanopy-daemon.log`, `Restart=always`, user root. Config `config.json` per directory (daemon name,
  `daemon_port`, server URL, site id, API key; keep it root-readable only in practice).
- A host that needs a second daemon identity (a Proxmox credential is assigned to a daemon, so the pve01 hypervisor has
  `Scanopy daemon pve01` on port 60073 and `pve-pve01` on port 60074) uses a second unit with its own config directory and log:
  `scanopy-daemon-2.service` with `--config-dir /etc/scanopy/daemon/scanopy-daemon-2 --log-file
  /var/log/scanopy/scanopy-daemon-2.log`. That unit was missing until 2026-10-12, so every discovery addressed to `pve-pve01`
  stayed `Pending` and its Proxmox data stopped refreshing on 2026-10-08.
- Proxmox discovery reads its API-token secret from `/root/.config/scanopy/proxmox-token.secret` on the daemon's own host, so
  only the hypervisor daemons can use the Proxmox credentials; VM daemons log harmless "credential malformed" warnings.
- A daemon only runs a discovery for which a `Scheduled` definition exists in Scanopy; `scanopy-discover` starts those definitions.

### Scanopy-side runtime settings (not in git)

These were applied through the Scanopy API on 2026-10-12 and are not managed by
any role; re-apply them if the Scanopy database is rebuilt:

- The `DockerSocket` credential is assigned to every VM daemon host that runs
  Docker, so discovery lists containers (not only networks).
- Each Docker VM daemon has an enabled `Scheduled` discovery definition with a
  daily 6-field cron (UTC) matching its slot in `monitoring_scanopy_discover_schedule`.
  The external trigger starts these definitions; Scanopy's own scheduler is not
  relied on (see above), and when it does fire first the trigger skips the host.
  The `ScanopyDiscoveryStale` alert fires when no host has been observed for 2 days.
- Some hosts had no `Scheduled` discovery definition at all (one lost it after a
  manual scan, two never had one), so a new schedule had to be created for them.
  After adding a Docker VM or running a manual scan, check that the host has an
  enabled `Scheduled` discovery.

## Rollback

Fastest, on the monitoring VM (read the backup names first):

```bash
sudo systemctl disable --now scanopy-sd.timer
ls /etc/prometheus/prometheus.yml.pre-scanopy-sd-*
```

Then either restore the chosen backup of `prometheus.yml` and send SIGHUP to
Prometheus, or, preferably, revert this change in git and converge so the file
is rendered rather than copied back by hand. The removed stale probe jobs are
kept in `/etc/prometheus/removed-stale-probe-jobs.20261011.yml`, and the
previous Alertmanager config in `/etc/alertmanager/alertmanager.yml.bak.*`.

To turn discovery off without reverting the rest, set
`monitoring_scanopy_sd_enabled: false` for the host and converge: the Scanopy
jobs disappear from `prometheus.yml` and no new Scanopy files are installed
(existing files stay on disk until removed by hand).

## ntfy user and topic setup (runtime state, not in git)

The topics `platform-monitoring-critical`, `platform-monitoring-warning`, and
`platform-monitoring-watchdog` need a read-write grant for the Alertmanager user.
These users and ACLs live in the ntfy database, not in `server.yml`, so an ntfy
converge does not remove them. To recreate them on the ntfy host:

```bash
sudo docker exec -it ntfy ntfy user add --role=user alertmanager-notify   # prompts for the password
sudo docker exec ntfy ntfy access alertmanager-notify platform-monitoring-critical rw
sudo docker exec ntfy ntfy access alertmanager-notify platform-monitoring-warning rw
sudo docker exec ntfy ntfy access alertmanager-notify platform-monitoring-watchdog rw
```

## Known caveats and follow-ups

- `ntfy_runtime` provisions ACLs only for the legacy topics. The warning and
  Watchdog topics used by the new routing are granted at runtime (above) and are
  not in `config/ntfy/topics.yaml`; a follow-up should add them there together
  with the tests that pin the provisioned `alertmanager` publish list.

- The ntfy `base-url` is rendered from `platform_domain`, which comes from the
  operator-local `.local/identity.yml` (not in git). If that value contains a
  mistyped apex, `/opt/ntfy/server.yml` carries it. Fix `platform_domain` in
  `.local/identity.yml`; the next ntfy converge re-renders `server.yml` and
  recreates the container. The Alertmanager receivers use the internal listener
  URL and are not affected.
- The 0docker and 0mcp hypervisor node exporters are published by Scanopy under
  their legacy `pve_*_host_*` job names (they became reachable on 2026-10-12), so
  they are no longer static jobs. If a future exporter must stay static, list it
  in `monitoring_prometheus_extra_scrape_jobs` and add its address to
  `monitoring_scanopy_sd_node_drop_address_regex` so it is not scraped twice. See
  `docs/runbooks/tailscale-metrics-grants.md` for the tailnet grants and listener
  changes behind this.
- `playbooks/services/prometheus-0own-node-exporter.yml` is a no-op while
  discovery is enabled, because Scanopy already publishes the 0own host exporter
  under the same job name.
