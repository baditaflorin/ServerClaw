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
| OpenObserve `remote_write` (DISABLED 2026-10-14: ~2,200 unqueried metric streams duplicating this Prometheus) | `monitoring_prometheus_remote_write_targets` (now `[]`; the commented restore block is in `inventory/host_vars/monitoring.yml`) | `monitoring_vm` | Password is never in git: `password_file` points at a systemd credential. |
| Prometheus credential drop-in | `monitoring_prometheus_remote_write_credentials` | `monitoring_vm` | `LoadCredentialEncrypted=` line only; the encrypted blob must already exist on the host and the role fails closed if it does not. |
| `scanopy_sd.py`, README, `extra-endpoints.json` | `roles/monitoring_vm/files/scanopy-sd/`, `monitoring_scanopy_sd_extra_endpoints` | `monitoring_vm` (`scanopy_sd.yml`) | Hosts that are switched off on purpose are listed in `monitoring_scanopy_sd_ignored_hosts` (rendered to `ignored-hosts.json`): while such a host does not answer it is not expected to have a node_exporter, is not published, and `NodeExporterMissing` stays quiet (currently `domainscope-pg-replica`, VM 153, whose replication slot is lost). Remove the entry when the VM runs again. |
| `scanopy-sd.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-sd.*.j2` | `monitoring_vm` | Timer is enabled, never restarted by a converge. |
| `/etc/scanopy-sd/api-key` | controller-local `monitoring_scanopy_sd_api_key_local_file` | `monitoring_vm` | root `0600`. See "Secrets". |
| `scanopy_retag.py`, README | `roles/monitoring_vm/files/scanopy-retag/` | `monitoring_vm` (`scanopy_retag.yml`) | Tags Docker bridge subnets in Scanopy. See "Docker bridge subnet tagging". |
| `scanopy-retag.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-retag.*.j2` | `monitoring_vm` | 15-minute timer; enabled, never restarted by a converge. |
| `/etc/scanopy-retag/api-key` | controller-local `monitoring_scanopy_retag_api_key_local_file` | `monitoring_vm` | root `0600`. See "Secrets". |
| `scanopy_discover.py`, `schedule.json`, README | `roles/monitoring_vm/files/scanopy-discover/`, `monitoring_scanopy_discover_schedule` | `monitoring_vm` (`scanopy_discover.yml`) | Starts the daily Docker VM discoveries through the API. See "External discovery trigger". |
| `scanopy-discover.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-discover.*.j2` | `monitoring_vm` | Timer runs every 15 minutes (minute 02/17/32/47); enabled, never restarted by a converge. Reuses `/etc/scanopy-retag/api-key`. |
| `scanopy_onboard.py`, `scanopy_onboard_hv.py`, `fleets.json`, README | `roles/monitoring_vm/files/scanopy-onboard/`, `monitoring_scanopy_onboard_*` | `monitoring_vm` (`scanopy_onboard.yml`) | Installs the daemon in new Proxmox guests. See "Automatic onboarding of new guests". |
| `scanopy-onboard.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-onboard.*.j2` | `monitoring_vm` | Timer runs every 15 minutes (minute 07/22/37/52); enabled, never restarted by a converge. Reuses `/etc/scanopy-retag/api-key`. |
| `/etc/scanopy-onboard/id_ed25519` | generated once by the role (`ssh-keygen`, `creates:`) | `monitoring_vm` | Dedicated key; its public half is a forced-command line on each hypervisor. |
| `scanopy_backup.py`, `scanopy_backup_hv.sh`, README | `roles/monitoring_vm/files/scanopy-backup/`, `monitoring_scanopy_backup_*` | `monitoring_vm` (`scanopy_backup.yml`) | Nightly pull of the Scanopy database. See "Database backup". |
| `scanopy-backup.service` / `.timer` | `roles/monitoring_vm/templates/scanopy-backup.*.j2` | `monitoring_vm` | Hourly at :20 UTC; enabled, never restarted by a converge. |
| `rules/inventory.yml`, `rules/zz-alertmanager-watchdog.yml` | `config/prometheus/rules/` | `monitoring_vm` | Reload only. `inventory.yml` also carries the `scanopy_retag`, `scanopy_discover` (incl. `ScanopyDaemonDown`) and `scanopy_onboard` alert groups. |
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
  **Current key (2026-10-14):** the file on the monitoring VM holds a **Member** key, `monitoring-automation (member)` (site
  Infrastructure, no expiry), kept in the vault as `scanopy_member_api`. It is used by retag, discover and onboard; verified calls: all
  list endpoints, `PUT` discovery and host, `POST` start-session, daemon provision and delete. The Admin key `scanopy api` (vault
  `admin_api`) is no longer used by any job and is kept for manual work only. To rotate the Member key: create a new one in the UI
  (API Keys, Create, permission Member, site Infrastructure), store it in the vault (`fleet-vault.py put scanopy_member_api ...`) and write
  it to `/etc/scanopy-retag/api-key` (root `0600`), then start the three services once and check they succeed.
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
  Deleting many Scanopy hosts on purpose (for example foreign hosts swept by a
  daemon) always trips it, and `ScanopySDStale` follows after 30 minutes because the
  guarded run is not a success: touch `accept-shrink` (as root, the directory is
  not world-readable) in the same session as the deletion. This was missed on
  2026-10-16 (125 to 94 hosts) and targets sat unrefreshed for 36 hours.
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

The schedule covers the Docker VM daemons (01:00 to 05:15 UTC), then each hypervisor's Proxmox daemon (`pve-0docker`, `pve-0mcp`,
`pve-0own`, `pve-0database`, `pve-0infer`) and the two host daemons for the hypervisors that need them (05:30 onward UTC) so each Proxmox VE inventory stays fresh. PVE01 remains the
technical hostname and SSH endpoint (`proxmox.0database.com`); its fleet and Scanopy identity is `0database`.

To add or move a host, edit `monitoring_scanopy_discover_schedule` in
`inventory/host_vars/monitoring.yml` (keep slots on distinct quarter hours) and
converge. The host's daemon must already have a `Scheduled` discovery definition in
Scanopy; the job does not create one. A daemon that is **not** in the schedule but whose
`Scheduled` definition is enabled with a daily quarter-hour cron (`0 M H * * *`, UTC) is
scheduled too (the inventory slot wins when both exist): that is how the onboarding job
hands over a new guest, so it is scanned every day without an inventory edit.

The same run reports **daemon liveness**: `scanopy_daemon_last_seen_age_seconds{daemon}` for
every daemon Scanopy knows (a healthy daemon polls about every 30 s), `scanopy_daemons_total`
and `scanopy_daemons_unreachable`. `ScanopyDaemonDown` fires when a daemon has been silent for
more than 10 minutes for 5 minutes: check the guest, `journalctl -u scanopy-daemon` inside it,
and the fleet's relay and host firewall.

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

### Scanopy daemons (one per guest and hypervisor)

Every running Proxmox guest (VM and container) and every hypervisor runs a Scanopy daemon (DaemonPoll mode, polls the server every
30 s; the server is on the 0docker hypervisor), 41 in all as of 2026-10-13. No role installs them; use this layout and procedure.

- Unit `scanopy-daemon.service`, `ExecStart=/usr/local/bin/scanopy-daemon --config-dir /etc/scanopy/daemon/scanopy-daemon
  --log-file /var/log/scanopy/scanopy-daemon.log`, `Restart=always`, user root. `config.json` holds the daemon name, port, server URL,
  site id and the daemon's own API key (root-only in practice). `scanopy-daemon install` writes all of this.
- **Server URL per fleet.** Guests use a private relay or tailnet address, and the daemon's
  `server_url` is that address on port 60072: `http://10.10.10.1:60072` (0docker, the server itself), `http://10.10.10.1:60072` (0mcp),
  `http://10.60.10.1:60072` (0own), `http://10.50.0.1:60072` (0database), and
  `http://10.70.10.1:60072` (0infer, bound to vmbr70). On 0mcp, 0own, 0database and 0infer this is a `scanopy-relay.socket` +
  `systemd-socket-proxyd` forwarding to the server's tailnet address. The 0infer host listens only on `10.70.10.1:60072` and forwards to
  `100.64.0.5:60072`; this covers VM704, which has no Tailscale interface. Keep the Tailscale API grant on the hypervisor only.
  The relay service runs as `nobody` with `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, and `ProtectHome=true`.
- **Relay rule.** The 0mcp hypervisor's `host.fw` lets the guest LAN reach the relay with one rule (`IN ACCEPT -i vmbr20 -source
  10.10.10.0/24 -dest 10.10.10.1 -p tcp -dport 60072`), rendered from `proxmox_host_additional_tcp_rules`
  (`inventory/host_vars/proxmox-host.yml`). It used to be one rule per guest; that blocked every guest the onboarding job installs
  without anyone listing it first (the daemon logs "Still unreachable"). The relay only forwards to a server that needs a per-daemon
  API key. The other hypervisors have no such list. `tests/test_monitoring_prometheus_codification.py` keeps the rule in the policy.
- **New guests are onboarded automatically** (see "Automatic onboarding of new guests"). To install one by hand, for example a VM whose
  guest agent does not answer, use `scripts/scanopy_daemon_rollout.py` (see its docstring for the targets file). It provisions the daemon through
  `POST /api/v1/daemons/provision`, which mints a key **bound 1:1** to the daemon record, and installs with only `--server-url` and
  `--daemon-api-key`. Do not create the key with `POST /api/v1/auth/daemon`: that makes a legacy site-shared key, the daemon keeps the nil
  id, and the server answers "Daemon context required" (HTTP 403). Reach for guests without an ssh alias through the hypervisor's guest
  agent (`qm guest exec`) to authorise a key, or `pct exec` for containers.
- **After a manual install:** a new daemon gets a weekly `Scheduled` discovery by default. Move it to a daily quarter-hour slot (the
  trigger adopts it, or add it to `monitoring_scanopy_discover_schedule`), and attach the `docker-socket-1` credential to the host
  of every guest that runs Docker. The onboarding job does both itself.
- A host that needs a second daemon identity (a Proxmox credential is assigned to a daemon, so the 0database hypervisor has `Scanopy daemon 0database`
  on port 60073 and `pve-0database` on port 60074) uses a second unit with its own config directory and log: `scanopy-daemon-2.service` with
  `--config-dir /etc/scanopy/daemon/scanopy-daemon-2 --log-file /var/log/scanopy/scanopy-daemon-2.log`. That unit was missing until
  2026-10-12, so discoveries addressed to `pve-0database` stayed `Pending` and its Proxmox data stopped refreshing on 2026-10-08.
- Proxmox discovery reads its API-token secret from `/root/.config/scanopy/proxmox-token.secret` on the daemon's own host, so only the
  hypervisor daemons can use the Proxmox credentials; VM daemons log harmless "credential malformed" warnings.
- A daemon only runs a discovery for which a `Scheduled` definition exists in Scanopy; `scanopy-discover` starts those definitions.
- **Setting up a new hypervisor's two daemons (done for 0infer on 2026-10-16; the steps are the same for any new Proxmox host).**
  1. Proxmox side (mirrors the other hypervisors): role `ScanopyGuestAgent` (`VM.GuestAgent.Audit`), user `scanopy@pve`, API token `discovery`
     with privilege separation, and the roles `PVEAuditor` + `ScanopyGuestAgent` on `/` for both the user and the token. The token secret is
     written by the command that creates it to `/root/.config/scanopy/proxmox-token.secret` (root, `0600`) so it never appears in a terminal.
  2. Scanopy side: provision the two daemon records (`POST /api/v1/daemons/provision`, names `Scanopy daemon <fleet>` and `pve-<fleet>`, the keys go
     straight into root-only files on the host), install with `scanopy-daemon install --mode daemon_poll --server-url http://100.64.0.5:60072`
     (the hypervisor talks to the server over the tailnet; its relay is for guests): the first on port 60073 with the default config dir, the second with
     `--daemon-port 60074 --config-dir /etc/scanopy/daemon/scanopy-daemon-2 --log-file /var/log/scanopy/scanopy-daemon-2.log --instance 2`
     (that creates `scanopy-daemon-2.service`). Delete the staging files with the keys afterwards.
  **Restrict the scan scope before the first discovery runs.** A Hetzner host whose public interface is an on-link /26 (0infer: `eno1 203.0.113.20/26`)
     shares that LAN with other customers; a daemon with the default scope ARP-sweeps and port-probes every neighbour. On 2026-10-16 the two 0infer
     daemons did exactly that and recorded 33 foreign hosts (157.90.1.128/26) before it was noticed. For a new Proxmox host: install the daemons with
     `--interfaces <internal bridge>` (config key `interfaces`, e.g. `["vmbr70"]`) so they never attach to the public interface, and set `subnet_ids`
     of their `Scheduled` discovery to the internal subnet only. Check `interfaced_subnet_ids` of the daemon (no public CIDR) and that no
     non-private subnet with foreign hosts appears under Subnets before leaving it alone. 0docker's public /27 only ever showed its own gateway; every
     other hypervisor is routed /32, but check each new one.
  3. Give each daemon's `Scheduled` discovery the cron of its slot in `monitoring_scanopy_discover_schedule`.
  4. Create the credential `pve-<fleet>-proxmox` (type ProxmoxApiToken, port 8006, token id `scanopy@pve!discovery`, secret from the file path above).
     Credentials are organisation-level: the Member key gets HTTP 403, use the Admin key (vault `admin_api`). Let the first discovery run (it creates the
     hypervisor's host record with its bridge address, 10.70.10.1 for 0infer), then assign the credential to that host and address and start the
     `pve-<fleet>` discovery again so the Proxmox VE data is read.


### Automatic onboarding of new guests

`scanopy-onboard` (systemd timer on the monitoring VM, every 15 minutes at minute 07/22/37/52) puts a Scanopy daemon on every running
Proxmox guest that has none. Per run:

1. For each hypervisor in `monitoring_scanopy_onboard_fleets` it runs `list` through the forced-command key (running, non-template
   VMs and containers with their MACs and real-interface IPv4 addresses; whether the guest is manageable) and asks Scanopy for its
   daemons and hosts.
2. A guest is **covered** when a daemon that has checked in is named after it (`<vm|ct>-<fleet>-<id>-<name>` or ending in its name),
   or one of its MACs, or an IPv4 address that belongs to exactly one daemon host, is on a daemon host. Addresses shared by several
   hosts (Docker bridges, the 10.10.10.0/24 range that exists in two fleets) prove nothing and are ignored.
3. A guest uncovered in two runs in a row (so a guest still being provisioned is left alone) is onboarded: `POST /api/v1/daemons/provision`
   mints a daemon record and a 1:1 key (re-provisioned when a record that never checked in exists), the hypervisor installs the daemon in
   the guest (`install`: containers through `pct exec`, VMs through the guest agent `qm guest exec --pass-stdin`; the key travels on stdin
   only), the job waits for the check-in (150 s), gives the daemon's `Scheduled` discovery the first free daily quarter-hour from 12:00 UTC
   (`scanopy-discover` adopts it), and attaches the `docker-socket-1` credential when the guest has Docker.
4. Guards: at most 2 installs per run; a failing guest backs off 30 minutes, doubling up to 24 hours (state in
   `/var/lib/scanopy-onboard/state.json`); a guest that already runs an active `scanopy-daemon` service but is unknown to Scanopy is
   reported, not reinstalled; `monitoring_scanopy_onboard_exclude` (`"<fleet>:<vm|ct>:<id>"`) skips a guest on purpose; the daemon version
   follows the fleet's most common version.

Metrics (textfile `scanopy_onboard.prom`): `scanopy_onboard_last_success_timestamp_seconds` (every hypervisor listed, no fatal error),
`scanopy_onboard_fleet_list_ok{hypervisor}`, `scanopy_onboard_guests_running{hypervisor}`, `scanopy_onboard_guests_uncovered`,
`scanopy_onboard_guests_unmanageable`, `scanopy_onboard_installs_this_run`, `scanopy_onboard_install_failures`. Alerts:
`ScanopyGuestWithoutDaemon` (uncovered or unmanageable guests for 3h), `ScanopyOnboardStale` (no clean run for 2h) and
`ScanopyOnboardMetricsAbsent`. A VM whose QEMU guest agent does not answer cannot be reached from its hypervisor: it is counted as
unmanageable, never touched, and needs the manual install.

A hypervisor under heavy disk load answers slowly: on 0own, during its nightly backups (03:15, 04:00, 04:30 jobs) even `qm list` takes about 40 s
and guest-agent calls time out. The wrapper (version 2) therefore queries guests in parallel with a 10 s limit each and reports a guest whose agent
does not answer as not manageable (it is still matched by MAC and name), and the job allows 150 s per hypervisor listing (`ONBOARD_SSH_TIMEOUT`) and
retries once. A hypervisor that still cannot be listed fails the run and, after 2 h, raises `ScanopyOnboardStale`.

**Hypervisor side (one-time per hypervisor, outside the role).** The monitoring VM reaches the hypervisors over their public SSH
(`root@example.net`, `root@10.10.10.1`, `root@203.0.113.14`, `root@proxmox.0database.com`); the tailnet does not allow tcp/22 from
it. On every hypervisor:

```bash
install -m 0755 scanopy_onboard_hv.py /usr/local/sbin/scanopy-onboard-hv        # copy kept at /opt/scanopy-onboard/ on the monitoring VM
# /root/.ssh/authorized_keys, one line, public key from /etc/scanopy-onboard/id_ed25519.pub on the monitoring VM:
command="/usr/local/sbin/scanopy-onboard-hv",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,from="10.10.10.40,203.0.113.1" ssh-ed25519 AAAA... scanopy-onboard
```

`from=` is the monitoring VM's permitted source address for that hypervisor. The 0mcp hypervisor sees its LAN and public addresses;
the 0infer hypervisor sees the monitoring VM's Tailscale address `100.64.0.4`. The key can run `list` and
`install <vm|ct> <id> <relay-url> <name> <version>` and nothing else; arguments are validated, the relay must be a
`http://10.x.x.x:60072` fleet relay or the exact private Scanopy address `http://100.64.0.5:60072`. After changing the wrapper, copy it
to every onboarded hypervisor again (`list` reports `wrapper_version`).

On the monitoring VM:

```bash
sudo python3 /opt/scanopy-onboard/scanopy_onboard.py --dry-run          # what it would do, changes nothing
sudo systemctl start scanopy-onboard.service && journalctl -u scanopy-onboard -n 30
sudo cat /var/lib/scanopy-onboard/state.json                            # sightings, failures, backoff per guest
```

Verified end to end on 2026-10-13: the daemon was stopped and deleted in Scanopy for container 107 (pve-exporter, 0docker) and VM 200
(0mcp-staging-runtime); the next run re-installed both, they checked in, got slots 12:00 and 12:15 UTC, and VM 200 got the Docker
credential. Roll back with `sudo systemctl disable --now scanopy-onboard.timer` or `monitoring_scanopy_onboard_enabled: false`.

**A guest that moved between fleets keeps its old daemon (VM 705 `infer-spire`, found 2026-10-23).** A VM that is migrated to another hypervisor
keeps `/etc/scanopy/daemon/*/config.json` with the old relay URL (here `http://10.50.0.1:60072` of the retired pve01) and the old daemon record, which is
then deleted: the daemon logs `403 Daemon context required`, `Daemon NOT ready`, and never retries. The onboarding job provisions a new record, but the
installer answers `skipped=already-active` and the job fails; later runs consider the guest covered because its host still shows a fresh "Scanopy Daemon"
service (up to 7 days), so only `ScanopyDaemonDown` (a record with `last_seen` never set, age 3650 days) tells. Fix: stop the old daemon in the guest
(`qm guest exec <vmid> -- systemctl stop scanopy-daemon` from the hypervisor), then call `onboard()` of `/opt/scanopy-onboard/scanopy_onboard.py` for that
guest from a root python on the monitoring VM (it reuses the provisioned record by name, so no duplicate), or delete the guest's service stop file and let the
job retry. Check afterwards: `scanopy_daemon_last_seen_age_seconds` low, a daily slot assigned. After moving a guest, stop its old daemon first.

### Compressing proxy for the web UI

The Scanopy server sends its API uncompressed: the topology page downloads about 16 MB, 11.7 MB of it one `GET /api/v1/topology/data` response (449 of the
459 subnets are Docker bridges, plus 1,500 services and 3,000 interfaces). A small Caddy container on the 0docker hypervisor, `scanopy-gzip`, serves the
same server compressed on the tailnet-only port **60080**: use `http://100.64.0.5:60080/?view=Workloads#topology` instead of port 60072 in the
browser. Measured on 2026-10-16: that response drops to 1.3 MB (gzip) / 1.2 MB (zstd), the whole page to about 3.4 MB; load time 14 s -> 12 s, because the
rest is the app's own start-up chain (about 5 MB of JavaScript, then several waves of list requests) and the browser's layout work. Daemons and relays
keep using 60072; nothing about the server changed, and the session cookie works on both ports.

```bash
# /root/scanopy-gzip/Caddyfile on the 0docker hypervisor
{ auto_https off
  admin off }
:8080 {
	encode zstd gzip
	reverse_proxy scanopy-server-1:60072 { flush_interval -1 }
}
docker run -d --name scanopy-gzip --restart unless-stopped --network scanopy_scanopy \
  -p 100.64.0.5:60080:8080 -v /root/scanopy-gzip/Caddyfile:/etc/caddy/Caddyfile:ro --memory 128m caddy:2-alpine
```

Remove it with `docker rm -f scanopy-gzip` (nothing else depends on it). The topology views: L3 Logical is IP networks only; **Workloads** shows the
containers per host. The hidden-subnet tag filter (Docker bridges) also hides the containers in L3 Logical.

### Database backup

The Scanopy Postgres is part of the compose project on the 0docker hypervisor, which PBS does not back up (it backs up guests); until
2026-10-13 the only copy was one dump from 2026-10-08 on the same host. `scanopy-backup` (systemd timer on the monitoring VM, hourly,
at :20 UTC) pulls a fresh `pg_dump` to the monitoring VM, which lives in another fleet (0mcp) and is itself in the nightly PBS job to
`own-pbs` (02:00), so there are two further copies one night later.

- The pull is `ssh root@example.net dump` with `/etc/scanopy-backup/id_ed25519`. On the hypervisor that key is a forced command
  (`/usr/local/sbin/scanopy-backup-hv`, the copy of `scanopy_backup_hv.sh` kept in `/opt/scanopy-backup/`) that only streams
  `docker exec scanopy-postgres-1 pg_dump ... | gzip`: `command="/usr/local/sbin/scanopy-backup-hv",no-pty,no-port-forwarding,
  no-agent-forwarding,no-X11-forwarding,from="10.10.10.40,203.0.113.1" ssh-ed25519 AAAA... scanopy-backup` in `/root/.ssh/authorized_keys`.
  Reinstall both after the hypervisor is rebuilt (see the next section for the host key).
- The dump is verified before it is kept: gzip integrity, at least 10 kB, the `PostgreSQL database dump complete` trailer, and the
  core tables (`daemons`, `hosts`, `discovery`, `api_keys`, `credentials`). It lands in `/var/backups/scanopy/scanopy-<UTC>.sql.gz`
  (root only, `0600`: it holds credential material), retention is tiered (every dump of the last 48 h plus the newest of each of the last 14 UTC days), and a failed run changes nothing. Metrics
  (`scanopy_backup.prom`): `scanopy_backup_last_success_timestamp_seconds` (kept across failed runs, so its age keeps growing),
  `scanopy_backup_last_attempt_success`, `scanopy_backup_last_size_bytes`, `scanopy_backup_files`. Alerts: `ScanopyBackupStale`
  (no verified dump for 36 h) and `ScanopyBackupMetricsAbsent`.
- **Weekly restore drill** (`scanopy-backup-drill.timer`, Sundays 04:10 UTC, needs Docker on the monitoring VM): restores the newest dump
  into a throwaway `postgres:17-alpine` container (no network, 512 MB, removed afterwards), fails on any `psql` error and requires rows
  in `daemons`, `hosts`, `discovery`, `api_keys` and `credentials`. Metrics `scanopy_backup_drill_*` (last success kept across failed runs,
  row counts per table); alerts `ScanopyBackupDrillStale` (no good drill for 10 days) and `ScanopyBackupDrillMetricsAbsent`. Keep the image's
  major version equal to the Scanopy database's (`monitoring_scanopy_backup_drill_image`). Run by hand with
  `sudo systemctl start scanopy-backup-drill.service`.
- Manual: `sudo systemctl start scanopy-backup.service`, `sudo python3 /opt/scanopy-backup/scanopy_backup.py --dry-run`.
  Roll back with `sudo systemctl disable --now scanopy-backup.timer` or `monitoring_scanopy_backup_enabled: false`.

**Restore** (rehearsed by hand on 2026-10-13 into a scratch database, and every week by the drill: 41 daemons, 81 hosts, 154 discoveries, 41 API keys and 5 credentials,
equal to live). The dump is plain SQL made with `--clean --if-exists`. Copy it to the new Scanopy host, stop the server container
(`docker compose stop server` in `/Users/live`), then load it into the (empty or existing) database and start the server again:

```bash
zcat scanopy-<UTC>.sql.gz | docker exec -i scanopy-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q'
```

To rehearse without touching the live database, create a scratch database first (`create database scanopy_restore_test`), load into
that with `-d scanopy_restore_test`, compare row counts, and drop it. A restored database keeps every daemon key, so the daemons
reconnect on their own; only a lost database needs the re-enrolment in the next section.

### Warm standby of the Scanopy server (monitoring VM)

Scanopy is an observation tool: Prometheus service discovery keeps its last good files while the server is down, and daemons retry. Real-time
replication is not worth its moving parts for a 72 MB database that the daemons can rediscover. What matters is how fast a replacement can serve the
daemon keys, credentials, tags and schedules that are not rediscoverable. The server's only state is the database (its data directory is empty;
its whole configuration is five settings), so a standby is the newest dump plus the same server image:

- **Data:** `scanopy-backup` dumps hourly (tiered retention, see "Database backup"); `scanopy-standby-sync` (hourly at :35 UTC) restores the newest
  dump into the persistent container `scanopy-standby-postgres` on the monitoring VM (0mcp fleet, a different hypervisor than the 0docker primary),
  only when a newer dump exists, and checks that daemons, hosts, discoveries, API keys and credentials have rows. Worst case a failover loses the
  last hour of discovery history.
- **Server:** `scanopy-standby-server` (the same image tag as the primary, `v0.17.22`) is defined in `/opt/scanopy-standby/docker-compose.yml` under
  the compose profile `failover` and never runs by default. `scanopy-standby-boot-test` (Sundays 04:40 UTC) starts it on `127.0.0.1:60099` against the
  restored data, waits for `/api/health`, lists the daemons through the API with the key of the retag/discover/onboard jobs (it is stored in the
  database, so a working answer proves the copy is a functioning Scanopy) and stops it again. First run on 2026-10-17: healthy after 16 s, 47 daemons.
- **Alerts:** `ScanopyStandbyStale` (standby not refreshed for 6 h), `ScanopyStandbyBootTestStale` (no good boot test for 10 days),
  `ScanopyStandbyMetricsAbsent`, `ScanopyStandbyFailoverActive` (the standby server is running: a failover is in progress or was forgotten).
- **Memory:** the always-on part is one Postgres container (limited to 256 MB); the server needs about 250 MB and only runs for the 10-20 s boot test
  or during a failover. The monitoring VM has 4 GB and is tight, so check `free -m` before a long failover.

**Failover** (the primary is gone or down for long; the standby carries on from the newest dump):

1. On the monitoring VM start the server on the tailnet address (the sync pauses itself while it runs, so the live data is not overwritten):
   `sudo STANDBY_BIND=100.64.0.4 STANDBY_PORT=60072 docker compose -f /opt/scanopy-standby/docker-compose.yml --profile failover up -d server`.
   The UI is then `http://100.64.0.4:60072`, the same login and keys as the primary.
2. Point the daemons at it. Guest daemons go through the relay on their hypervisor (`scanopy-relay.service`, `systemd-socket-proxyd <target>:60072`):
   on the 0mcp, 0own, 0database and 0infer hypervisors change the target in `/etc/systemd/system/scanopy-relay.service` from `100.64.0.5:60072` to
   `100.64.0.4:60072` (`sed -i 's/100.64.0.5:60072/100.64.0.4:60072/' /etc/systemd/system/scanopy-relay.service && systemctl daemon-reload && systemctl restart scanopy-relay.service`).
   The hypervisors' own daemons already use their local relay (done 2026-10-17), so no `config.json` edits are needed; every daemon in the fleet reconnects
   by itself within a minute. Reachability is in place and was verified: the Tailscale grant (`config/tailscale/policy.hujson`) and the monitoring VM
   firewall (`network_policy.guests.monitoring.allowed_inbound`, tcp/60072 from the four hypervisors) both allow it; before the standby server is started a
   hypervisor gets "connection refused" from `100.64.0.4:60072`, which is the expected healthy answer.
3. Check: `scanopy_daemon_last_seen_age_seconds` low for all daemons, the jobs on the monitoring VM succeed (they use the relay on 10.10.10.1),
   `ScanopyStandbyFailoverActive` fires (expected, it tells the next person).

**Failback** (the primary is healthy again): stop writes by pausing nothing is needed; dump the standby database
(`docker exec scanopy-standby-postgres pg_dump -U postgres -d scanopy --no-owner --clean --if-exists | gzip > /root/failback.sql.gz`), restore it into the primary
as in "Database backup", repoint the relays back to `100.64.0.5:60072`, then stop the standby server
(`docker compose -f /opt/scanopy-standby/docker-compose.yml --profile failover rm -sf server`); the hourly sync resumes by itself.

Roll the standby back with `systemctl disable --now scanopy-standby-sync.timer scanopy-standby-boot-test.timer` and
`docker compose -f /opt/scanopy-standby/docker-compose.yml down -v`, or `monitoring_scanopy_standby_enabled: false` and a converge (installed files stay).

### Recovery after the Scanopy server or the 0docker hypervisor is rebuilt

The Scanopy server, its Postgres and the hypervisor-local daemon run as a compose project on the **0docker hypervisor** (not in a
guest), so a PBS restore of the guests does not bring them back; `/root/scanopy-backups` is on the same host. While that hypervisor is
down every daemon is unable to poll and the jobs on the monitoring VM fail safe: `scanopy-discover` and `scanopy-onboard` exit 1 on
the first API call and change nothing, and `ScanopyDiscoverStale`, `ScanopyOnboardStale`, `ScanopySDStale` and the `*MetricsAbsent`
alerts fire after their delays. `ScanopyDaemonDown` stays silent on purpose in that case: the liveness metrics come from the API, so
they disappear with it. Do not read the missing alert as "all daemons fine".

When the hypervisor is back:

1. **Host key.** The onboarding key pins each hypervisor in `/etc/scanopy-onboard/known_hosts` (`accept-new`: a changed key is
   refused, never auto-accepted). A rebuilt 0docker hypervisor has new host keys. Verify the new fingerprint out of band (Hetzner
   console), then remove the old `example.net` line on the monitoring VM (`sudo ssh-keygen -f /etc/scanopy-onboard/known_hosts -R
   example.net`); the next run records the new key. Never remove it just to make the alert stop.
2. **Hypervisor side.** A reinstalled hypervisor lost `/usr/local/sbin/scanopy-onboard-hv` and the forced-command line in
   `/root/.ssh/authorized_keys`; reinstall both as described above (the wrapper copy is `/opt/scanopy-onboard/scanopy_onboard_hv.py`).
3. **Server data.** If the Scanopy database was restored (from `/var/backups/scanopy`, see "Database backup"), nothing else is needed:
   daemons reconnect with their existing keys. If it was **lost** (no usable dump), every daemon key is invalid: create the organization, site, admin API key (store it as vault `admin_api` and in
   `/etc/scanopy-retag/api-key`), the `docker-socket-1` credential (update `monitoring_scanopy_onboard_docker_credential_id` and
   `monitoring_scanopy_onboard_site_id`), then re-enroll each guest with `scripts/scanopy_daemon_rollout.py` (it removes the old
   service and config and installs a freshly provisioned daemon). `scanopy-onboard` will not do this itself: it reports a guest that
   already runs an active `scanopy-daemon` but is unknown to Scanopy as a failure (`already active`) and leaves it alone.
4. **Daemons that started during the outage stay down.** A daemon that boots while the server is unreachable logs `Daemon NOT ready
   (Startup announcement failed)` and never retries (seen on 2026-10-13 with VM 650 after a reboot at the same time as the outage).
   `ScanopyDaemonDown` fires for it; run `sudo systemctl restart scanopy-daemon` inside the guest.
5. **0mcp relay rule.** The hypervisor's `host.fw` is rendered from `proxmox_host_additional_tcp_rules`; on 2026-10-13 a different render
   replaced the live file at 09:48 UTC and dropped the Scanopy relay rule and the monitoring 9102 scrape rules, which cut all 18 0mcp
   daemons off. If `scanopy_daemon_last_seen_age_seconds` is high only for 0mcp guests, check `grep 60072 /etc/pve/nodes/*/host.fw`
   on the 0mcp hypervisor first.
6. Check `sudo python3 /opt/scanopy-onboard/scanopy_onboard.py --dry-run` and `sudo python3 /opt/scanopy-discover/scanopy_discover.py
   --dry-run` before the next timer run; both should report no errors.

### Primary server compose file (0docker hypervisor, not in git)

The compose project `scanopy` (server + postgres) lives in `/Users/live` on the 0docker hypervisor (`docker-compose.yml`, `.env` 0600 with
`POSTGRES_PASSWORD`, `data/` bind-mounted into the server, named volume `scanopy_postgres_data`). The original file was found missing on 2026-10-17 while the
containers kept running (they carry the labels `com.docker.compose.project.config_files=/Users/live/docker-compose.yml`), so it was rebuilt from
`docker inspect`: same image `ghcr.io/scanopy/scanopy/server:v0.17.22` (+ `postgres:17-alpine`), port 60072, env (`SCANOPY_DATABASE_URL`, `SCANOPY_PUBLIC_URL=http://localhost:60072`,
`SCANOPY_INTEGRATED_DAEMON_URL=http://host.docker.internal:60073`, `SCANOPY_WEB_EXTERNAL_PATH=/app/static`, log level info), `host.docker.internal:host-gateway`, network
`scanopy_scanopy`, healthchecks and labels (`service: scanopy`, `org.scanopy.deploy_mode: downtime`). Postgres renders with the same config hash as the running container;
the server does not (some cosmetic field is unrecoverable), so a `docker compose up -d` recreates the server once with the same image and data. The embedded daemon
(`scanopy-daemon`: host network, privileged, docker.sock, volume `scanopy_daemon-config`) is not in the file but carries the project label: never use
`--remove-orphans`. The warm-standby compose (`templates/scanopy-standby-compose.yml.j2`) is the same shape. For an upgrade change the image tag in the file first,
take a dump (`scanopy-backup.service`), then `docker compose up -d` in `/Users/live`.

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
