# Fleet Observability And Postgres Backup Roles

This runbook covers `playbooks/fleet-observability.yml`, the four `lv3.platform.fleet_*` roles behind it and
`inventory/fleet-observability.yml`. They put the changes that were made by hand on 2026-10-11 and 2026-10-12 on the 0mcp,
0docker, 0database and 0own hosts under version control. **Nothing here runs by default**: no Makefile target, no
`site.yml` import, no CI job and no scheduler references the playbook, and it refuses to start without `--limit`.

## How the repository models hosts (survey)

| Surface | Covers | Notes |
|---|---|---|
| `inventory/hosts.yml` (generated from `proxmox_guests` in `inventory/host_vars/proxmox-host.yml`) | the 0mcp hypervisor (`proxmox-host`) and its guests | The only inventory `ansible.cfg` loads. |
| `lv3.platform.linux_guest_firewall` + `network_policy.guests.<name>` | 0mcp guests only | Rules come from the `proxmox_guests` data. The `nginx` guest's monitoring-only tcp 9100 rule lives here (PR #299). |
| `lv3.platform.proxmox_tailscale`, `proxmox_tailscale_proxy` | the 0mcp hypervisor | `tailscale up` with a full flag set; `lv3-tailscale-proxy-*` units. |
| `inventory/build_server.yml`, `hosts-docker.yml` | one build VM, a Docker dev stack | Explicit `-i` only. |
| (new) `inventory/fleet-observability.yml` | 0docker, 0database, 0own (seeded from `ssh-fleet-sync/00-fleet.conf`, host names are the SSH aliases) and the 0mcp hypervisor | Explicit `-i` only. Role groups (`fleet_node_exporter_hosts`, ...) name the hosts that have something to converge; the other hosts are inventory seeds. |

The 0docker, 0database and 0own fleets had no infrastructure-as-code before this change.

## Design decisions

- **Separate inventory and playbook, never a default.** `inventory/hosts.yml` is generated from the 0mcp topology and
  `ansible.cfg` loads only that file, so the new hosts live in `inventory/fleet-observability.yml`, used with an explicit
  `-i`. The playbook is not imported by `site.yml`, a Makefile target or CI, and its first play fails unless `--limit` names
  at most one host. Several of these hosts are production hypervisors; a typo must not become a fleet-wide converge.
- **Host names are the SSH aliases** from `ssh-fleet-sync/00-fleet.conf`, so ProxyJump, user and key stay in the operator's
  SSH config and no connection detail is duplicated in git.
- **Read, compare, write only on a difference.** Each role reads the live value (marked `check_mode: false` so `--check`
  reports real drift) and runs a write only when it differs. Nothing is ever deleted: no unit removal, no token or user
  deletion, no namespace creation.
- **Data, not copies.** The exporter port arrangement is declared per host (`listen_addresses`, `socket_proxies`,
  `tailscale_serve_tcp`) and checked as a whole, so moving a proxy to another port is a one-line inventory change.
- **Existing mechanisms are reused where they fit.** The 0mcp `nginx` rule stays in `network_policy` (rendered by
  `linux_guest_firewall`); `fleet_guest_firewall` uses the same rule vocabulary for guests that policy cannot describe.
  The `lv3-tailscale-proxy-*` units of `proxmox_tailscale_proxy` use a different prefix, so that role never removes the
  `z*-metrics-proxy` units this one renders. `proxmox_tailscale` re-runs `tailscale up` with a full flag set, which would
  reset node settings on other fleets; `fleet_tailscale_node` uses `tailscale set --advertise-routes` instead.

## Running it safely

Every run is one host, check mode first. The first play asserts that `--limit` is set, is not `all`/`*`, and matches at
most `fleet_observability_max_hosts` (1) hosts.

```sh
# 1. What would change? Read-only probes still run; look for DRIFT lines and changed tasks.
ansible-playbook -i inventory/fleet-observability.yml playbooks/fleet-observability.yml \
  --limit 0own_github_mirror --check --diff

# 2. Compare the rendered files with the live host independently of Ansible (read-only ssh).
python3 scripts/fleet_observability_render.py diff-live 0own_github_mirror

# 3. Apply to that one host, optionally one concern at a time.
ansible-playbook -i inventory/fleet-observability.yml playbooks/fleet-observability.yml \
  --limit 0own_github_mirror --tags exporter
```

Tags: `exporter` (node_exporter, textfile directory, socket proxies, `tailscale serve`), `tailscale` (advertised routes),
`firewall` (guest nftables), `backup` (vzdump hook/job, pgBackRest preparation, PBS user/ACL/prune job).

`--check` caveats: `command` tasks do not run in check mode, so writes made with `pvesh`, `proxmox-backup-manager`,
`tailscale set`, `tailscale serve` and `nft` show as skipped; the preceding read tasks run for real and print `DRIFT:`
lines that say what the write would change. Files (`template`, `lineinfile`, `file`) show a normal diff.

### Order of hosts

Lowest blast radius first; stop at the first unexpected diff.

1. Guest exporters: `0own_pyroscope_canary`, `0own_openobserve`, `0docker_scrapetheworld`, `0docker_pve_exporter`,
   `0docker_nginx`, `0docker_docker`.
2. `0own_github_mirror` (exporter, then `--tags firewall`; keep a second SSH session open for the first reload).
3. `0docker_builder` (`tailscale serve` only changes if the forward is missing).
4. `0own_pbs` (`--tags backup` first: it must exist before the hypervisor job), then `0database_bastion`, then
   `0database_postgres`.
5. Hypervisors: `0own_bastion` (`--tags tailscale`), `0docker_bastion`, last `operator-bastion`.

### What a first converge changes (live-vs-rendered, 2026-10-12)

`python3 scripts/fleet_observability_render.py diff-live <host>` was run read-only against every modelled host.

| Host | Difference between live and rendered |
|---|---|
| `operator-bastion`, `0docker_bastion`, `0docker_docker`, `0docker_nginx`, `0docker_pve_exporter`, `0docker_builder`, `0docker_scrapetheworld`, `0own_pbs`, `0own_openobserve`, `0own_pyroscope_canary`, `0own_bastion`, `0database_bastion` exporter | none (ARGS line, textfile directory ownership, proxy units, `tailscale serve` forward and advertised routes are identical) |
| `0own_github_mirror` | none (`/etc/nftables.conf` identical) |
| `0database_bastion` | `/usr/local/sbin/vzdump-pg-metrics-hook` is replaced (the fix below, header comments); the job comment loses the stale "DISABLED until ..." text |
| `0database_postgres` | `pgbackrest.conf` gains two comment lines; `pgbackrest-daily` gets a header comment and its default stanza changes from `prod` to `main` |
| `0own_pbs` | none |

Files that change get a timestamped `.bak` copy next to them (`backup: true`). The exporter restarts only when its `ARGS`
line changes, which is not expected on any host today.

## What is codified

| Item | Role | Where the data lives |
|---|---|---|
| node_exporter listen address(es), textfile directory and its owner/mode, extra flags | `fleet_node_exporter` | host variables `fleet_node_exporter_*` |
| 0docker hypervisor socket proxy (tailnet `:9100` to the internal exporter), 0mcp runtime-general proxy (`:9101`) | `fleet_node_exporter` | `fleet_node_exporter_socket_proxies` |
| 0mcp hypervisor build-metrics proxy `woodpecker-0exec-build-metrics-proxy.{socket,service}`: tailnet `100.64.0.6:9103` (`FreeBind=true`) to `10.10.10.30:9100` (docker-build VM exporter); consumer CT108 `100.114.37.21` | `fleet_node_exporter` | `fleet_node_exporter_socket_proxies` (`free_bind: true`, `consumer`, `consumer_grants`) |
| 0docker hypervisor stale `woodpecker-exec-proxy@9100.socket`: kept stopped and disabled (`state: disabled`) | `fleet_node_exporter` | `fleet_node_exporter_socket_proxies` |
| PVE host firewall line `100.114.37.21/32 -> 100.64.0.6 tcp 9103` on the 0mcp hypervisor | `proxmox_security` (`host.fw.j2`) | `proxmox_host_additional_tcp_rules` in `inventory/host_vars/proxmox-host.yml` |
| Tailnet grant `tag:builder-metrics-controller -> 100.64.0.6/32 tcp:9103` and its policy test | `config/tailscale/policy.hujson` | applied with `scripts/tailscale_policy_sync.py` (see `docs/runbooks/tailscale-metrics-grants.md`) |
| CT108 `tailscale serve --tcp=9100` to the internal exporter | `fleet_node_exporter` | `fleet_node_exporter_tailscale_serve_tcp` |
| github-mirror nftables (tcp 9100 only from the monitoring VM on `tailscale0`) | `fleet_guest_firewall` | `fleet_guest_firewall_allowed_inbound` |
| Advertised subnet routes (0docker hypervisor `.109/32`, 0own hypervisor `.50/32`, plus the pre-existing ones) | `fleet_tailscale_node` | `fleet_tailscale_node_advertise_routes` |
| vzdump metrics hook, PBS storage `own-pbs-0database` (non-secret fields), job `pg-primary-daily-pbs` (VM 100, snapshot, 02:30, bwlimit 100000 KiB/s) | `fleet_pg_backup` (`pve_backup`) | `fleet_pg_backup_pve_*` |
| `/etc/pgbackrest` layout, `pgbackrest.conf`, `pgbackrest-daily`, prepared (not installed) service and timer | `fleet_pg_backup` (`pgbackrest`) | `fleet_pg_backup_pgbackrest_*` |
| own-pbs realm user, ACLs on the `0database` namespace, prune job `prune-0database` | `fleet_pg_backup` (`pbs_server`) | `fleet_pg_backup_pbs_*` |
| `fleet-docker-prune` script, service and daily timer (04:30 UTC, unused images and BuildKit cache older than 7 days; textfile metrics `fleet_docker_prune_*`) on the 0mcp docker-build guest | `fleet_docker_prune` | `fleet_docker_prune_*`; host `0mcp_docker_build` in group `fleet_docker_prune_hosts` |
| `fleet-hypervisor-memory-reclaim` script, service and 5-minute timer (runs `echo 2 > /proc/sys/vm/drop_caches` while MemAvailable is under 10%; textfile metrics `fleet_hypervisor_memory_reclaim_*`) on the 0mcp hypervisor | `fleet_hypervisor_memory_reclaim` | `fleet_hypervisor_memory_reclaim_*`; host `operator-bastion` in group `fleet_hypervisor_memory_reclaim_hosts` |
| Hypervisor memory alerts (`FleetHypervisorMemAvailableLow` <5% 10m, `FleetHypervisorMemAvailableCritical` <3% 5m, `FleetHypervisorSwapExhausted` >90% swap 15m; every `role="hypervisor"` node_exporter) | `monitoring_vm` | `config/prometheus/rules/fleet-hypervisor-memory.yml` |
| Alertmanager self-monitoring: scrape job `alertmanager` (127.0.0.1:9093/metrics), `AlertmanagerDown`, `AlertmanagerNotificationsFailing`, `AlertmanagerStatePersistenceFailing` | `monitoring_vm` | `prometheus.yml.j2`, `config/prometheus/rules/alertmanager-self.yml` |
| Root-filesystem alerts (`FleetRootFilesystemLow` <15% free 30m, `FleetRootFilesystemCritical` <7% 10m, `FleetRootFilesystemFillingFast` predicted full within 24h) and `FleetDockerPruneStale` | `monitoring_vm` | `config/prometheus/rules/fleet-disk.yml` (copied to `/etc/prometheus/rules/fleet-disk.yml` on the monitoring VM) |
| Dead-man and finding alerts for the pool guardian and horizon loops on the 0docker builder (`FleetPoolGuardianSlow`, `FleetPoolGuardianSilent`, `FleetPoolGuardianLockedOut`, `FleetPoolGuardianNotReporting`, `FleetPoolGuardianCriticalFinding`, `FleetPoolGuardianCircuitOpen`, `FleetPoolGuardianPaused`, `FleetHorizonSilent`, `FleetHorizonNotReporting`, `FleetHorizonCriticalFinding`) | `monitoring_vm` | `config/prometheus/rules/fleet-loops.yml` (copied to `/etc/prometheus/rules/fleet-loops.yml` on the monitoring VM) |
| the nginx guest's tcp 9100 rule | already in PR #299: `network_policy.guests.nginx` rendered by `linux_guest_firewall` | `inventory/host_vars/proxmox-host.yml` |

### Docker prune and disk alerts

Why: a Woodpecker `test` step on the docker-build guest (VM 130) failed with `no space left on device` while compiling
Go (`/tmp/go-build...` is in the step container's writable layer under `/var/lib/docker` on `/`). Nothing pruned the
host and `/` stood at 83% with 91 images (two 2.4 GB Playwright images among them).

- The timer removes only unused images and old build cache; it does not touch containers, volumes or networks.
- The alert rules apply to every host the 0mcp Prometheus scrapes with `mountpoint="/"`. That includes docker-build
  (`10.10.10.30`), Builder CT108 (`100.114.37.21`) and the 0docker hypervisor (`100.64.0.5`), which it reaches over
  Tailscale. A fleet-wide `/` alert for hosts that only the 0docker Prometheus scrapes would live with that fleet's
  monitoring, not here.
- Verified live on 2026-10-12: the rules load healthy, `node_filesystem_avail_bytes{mountpoint="/"}` returns docker-build,
  and `fleet_docker_prune_last_success_timestamp_seconds` is scraped from it. The first evaluation put CT108 (12% free)
  and the 0docker hypervisor (11.3% free) in `FleetRootFilesystemLow` pending.
- The textfile directory `/var/lib/prometheus/node-exporter` is the Debian package default and is the one the
  docker-build node_exporter reads (it already holds `nvme.prom`, `smartmon.prom` and the Woodpecker build metrics).

First run, one host, check mode first:

```bash
ansible-playbook -i inventory/fleet-observability.yml playbooks/fleet-observability.yml \
  --limit 0mcp_docker_build --tags docker-prune --check --diff
```

### The vzdump hook fix

After a successful run `pg_backup_size_bytes` and `pg_backup_duration_seconds` stayed at their old value (0 on a fresh
install). vzdump exports `LOGFILE` to hooks only for directory targets (`PVE/VZDump.pm`: `$task->{logfile}` is set only
with a `dumpdir`); for a Proxmox Backup Server target the task log is `/var/log/vzdump/<vmtype>-<vmid>.log`, so the
`log-end` branch never found a file. The codified hook falls back to that path, takes the vmid label from its third
argument (vzdump does not export `VMID`), ignores a stale log after a failed run, and keeps a wall-clock duration from
`backup-start` to `backup-end` as a fallback. `tests/test_fleet_observability_roles.py` runs the rendered hook with bash
against a stub vzdump layout, with and without `LOGFILE`.

- `FleetRootFilesystemFillsWithin14Days` (warning, added 2026-10-13): fires when the 3-day trend leaves a root filesystem that is less than 40% free out of space within 14 days (6 h wait). The 24-hour rule leaves a day to react; this one leaves time to prune data or order storage (the 0database Postgres primary had about a week left when it was found by accident). The last 24 hours must trend the same way, so a one-off step (a restore, a cache warm-up) older than a day stays quiet; a step less than a day old can still warn. Tests: `tests/promtool/fleet_disk_forecast_test.yml`.

## Secrets stay out of git

The roles only reference these, by path, and only check existence, owner and mode (never read or print them):

| Reference | Host | Created by |
|---|---|---|
| `/etc/pve/priv/storage/own-pbs-0database.pw` (PBS API token secret) | 0database hypervisor | `pvesm add pbs` (operator) |
| `/etc/pgbackrest/conf.d/10-repo-cipher.conf` (`repo1-cipher-pass`) | pg-primary | operator, copied to the password manager; backups are unreadable without it |
| PBS API token `backup-0database@pbs!vzdump-0database` | own-pbs | `proxmox-backup-manager user generate-token` (operator) |

## Operator-managed on purpose

| Item | Why |
|---|---|
| The tailnet policy (grants, auto-approvers, tests) | control plane, codified by a separate workstream |
| Creating the PBS storage entry, the API token, the pgBackRest passphrase | secrets |
| The PBS namespace `0database` (verified, not created), the other namespaces and the `own-pbs-retention` prune job | not part of this change |
| `archive_mode`, `archive_command`, the pgBackRest repository choice, installing the pgBackRest timer | needs a Postgres restart and a decision; `archive_mode` stays off. The role can install the timer only when `fleet_pg_backup_pgbackrest_timer_enabled: true`, a repository is set and the exporter textfile collector is on |
| `.prom` writers (`proxmox-capacity-metrics`, `pve-host-health-metrics`, apt/smartmon/nvme scripts, Woodpecker resource exporter) | owned by their repositories; the role only owns the directory |
| Hosts pre-dating this change with their own exporter setup: 0own hypervisor (tailnet-only drop-in), `0docker_docker_prod`, `0own_build_worker`, `0database_builder`, `0database_runtime_1` | not modelled; inventory seeds only |
| Prometheus targets | Scanopy file_sd publishes the exporters |

## NEEDS DECISION

1. **Resolved 2026-10-12 (user approved removal): the stale grant and cluster rule for the old build-metrics port `:9100`.**
   `woodpecker-0exec-build-metrics-proxy.socket` moved from tailnet `:9100` (now the hypervisor exporter) to `:9103`.
   The tailnet grant `tag:builder-metrics-controller -> 100.64.0.6/32 tcp:9100` and the cluster firewall rule
   `100.114.37.21/32` tcp 9100 were removed from the live tailnet policy, `config/tailscale/policy.hujson` and
   `proxmox_cluster_additional_tcp_rules`. Nothing used them. The monitoring VM keeps `tag:prometheus-monitoring ->
   100.64.0.6/32 tcp:9100`.
2. **`woodpecker-exec-proxy@9100.socket` on the 0docker hypervisor** was enabled but inactive and is now **disabled**
   live and modelled as `state: disabled` (its drop-in forwarded to the same `10.10.10.1:9100` as
   `zdocker-hypervisor-metrics-proxy`, and both want the same tailnet `:9100`). The role keeps it stopped and
   disabled and never renders it; the `@9000` instance (Woodpecker agent path) is not touched. Retire the unit files
   and the `woodpecker-exec-proxy@9100.service.d` drop-in only with the user's OK.
3. **pg-primary exporter has no textfile collector flag** (live), but the prepared `pgbackrest-daily` wrapper writes its
   metrics into the textfile directory. **Recommendation:** set `fleet_node_exporter_textfile_dir` for `0database_postgres`
   in the same window that enables archiving; the role refuses to enable the timer without it.
4. **Exporters bound to tailnet addresses start before `tailscale0` may have its address after a reboot.** One host
   (`0database_builder`) already has a drop-in that waits for the address. **Recommendation:** adopt the same drop-in
   fleet-wide in a follow-up; not included to keep this change a pure codification.

## Build-metrics proxy (0mcp hypervisor)

```
CT108 (0docker-builder, tailnet 100.114.37.21, userspace tailscaled, socks5 127.0.0.1:1055)
   -> tailnet grant  tag:builder-metrics-controller -> 100.64.0.6/32 tcp:9103
   -> PVE host.fw    IN ACCEPT -source 100.114.37.21/32 -dest 100.64.0.6 -p tcp -dport 9103
   -> woodpecker-0exec-build-metrics-proxy.socket  ListenStream=100.64.0.6:9103  FreeBind=true
   -> systemd-socket-proxyd 10.10.10.30:9100  (docker-build VM130 node_exporter, nodename=docker-build)
```

Port plan of the tailnet address `100.64.0.6`: `:9100` hypervisor exporter, `:9101` runtime-general proxy, `:9102`
hypervisor exporter, `:9103` build-metrics proxy.

Why `FreeBind=true`: a socket unit binds its address when it starts. When tailscaled restarts, `tailscale0` can briefly
have no `100.x` address and the bind fails with `Cannot assign requested address`; that is what killed the proxy on
2026-10-11 00:53 and left it dead until someone noticed. `FreeBind=true` (`IP_FREEBIND`) lets the socket bind an
address that is not (yet) assigned, so it keeps listening across the restart and the connection works as soon as the
address is back.

Checks (read-only):

```sh
ssh operator-bastion 'systemctl show -p FreeBind -p Listen woodpecker-0exec-build-metrics-proxy.socket; ss -ltn | grep :9103'
ssh 0docker_bastion 'pct exec 108 -- bash -lc "curl -s --socks5-hostname 127.0.0.1:1055 http://100.64.0.6:9103/metrics | grep -m1 ^node_uname_info"'   # nodename="docker-build"
python3 scripts/fleet_observability_render.py diff-live operator-bastion
python3 scripts/fleet_observability_render.py diff-live 0docker_bastion
scripts/tailscale-policy-ct108.sh plan        # semantic changes must be empty
```

## Rollback

| Change | Rollback |
|---|---|
| Exporter `ARGS` line | restore the timestamped `/etc/default/prometheus-node-exporter.<...>~` backup the converge created, `systemctl restart prometheus-node-exporter` |
| Socket proxy units | restore the old unit text (or remove the two files), `systemctl daemon-reload`, `systemctl restart <name>.socket` |
| `FreeBind=true` on a proxy socket | delete the line from `/etc/systemd/system/<name>.socket` (or restore its `.bak.<epoch>` copy), `systemctl daemon-reload`, `systemctl restart <name>.socket` |
| `tailscale serve` forward | `tailscale serve --tcp=9100 off` (then re-add the previous target if there was one) |
| Advertised routes | `tailscale set --advertise-routes=<previous list from the DRIFT line>` |
| nftables on the guest | restore the `.bak` copy of `/etc/nftables.conf`, `nft -f /etc/nftables.conf`; a console session keeps working if SSH is cut |
| vzdump hook / pgBackRest files | restore the `.bak` copy; the hook only writes the `.prom` file and the state directory |
| PBS storage or job settings | the DRIFT line prints the old value: `pvesh set /storage/<id> --<key> <old>` or `pvesh set /cluster/backup/<id> --<key> <old>` |
| Docker prune timer | `systemctl disable --now fleet-docker-prune.timer`, remove the two unit files and `/usr/local/sbin/fleet-docker-prune`, `systemctl daemon-reload`; pruned images are re-pulled on demand |
| Build host cache trim alerts | delete `/etc/prometheus/rules/fleet-job-caches-trim.yml` on the monitoring VM and reload Prometheus; also remove the name from `monitoring_prometheus_adopted_rule_files`, or the next converge puts it back |
| Disk alert rules | delete `/etc/prometheus/rules/fleet-disk.yml` on the monitoring VM and reload Prometheus |
| Fleet loops rules | delete `/etc/prometheus/rules/fleet-loops.yml` on the monitoring VM and reload Prometheus |
| CI cache prune alerts | delete `/etc/prometheus/rules/fleet-ci-cache-prune.yml` on the monitoring VM and reload Prometheus; also remove the name from `monitoring_prometheus_adopted_rule_files`, or the next converge puts it back |
| Hypervisor memory reclaim timer | `systemctl disable --now fleet-hypervisor-memory-reclaim.timer`, remove the two unit files and `/usr/local/sbin/fleet-hypervisor-memory-reclaim`, `systemctl daemon-reload` |
| Hypervisor memory / Alertmanager self rules | delete `/etc/prometheus/rules/fleet-hypervisor-memory.yml` / `alertmanager-self.yml`, reload Prometheus; the `alertmanager` scrape job: restore `/etc/prometheus/prometheus.yml.pre-am-scrape-<ts>` |
| PBS ACL / prune job | `proxmox-backup-manager acl update <path> NoAccess --auth-id <id>` / `prune-job update` with the old value; user and token deletion is deliberately not automated |

## Validation

- `tests/test_fleet_observability_roles.py`: offline template rendering (exporter ARGS, proxy units, nftables, hook,
  pgBackRest), the hook executed with bash against a stub vzdump layout, the port-plan collision check, the playbook
  guard, the secret scan and the role conventions.
- `scripts/fleet_observability_render.py diff-live <host>`: read-only live-vs-rendered comparison (files, directory
  ownership, tailscale routes and serve, PBS storage and job, PBS user/ACL/prune job). Secret files are only `stat`-ed.
- `tests/test_fleet_docker_prune_role.py`: the prune script run with bash against stub `docker` and `df` (only image
  and builder prune, textfile metric written atomically, none written on failure), the units, the inventory wiring and
  the disk alert rules.
- Not run locally: `ansible-lint`, `yamllint`, `ansible-playbook --syntax-check` (none installed on the authoring machine).
  Run them in CI or on the controller before the first converge.

## own-pbs datastore capacity (added 2026-10-13)

The datastore `own-pbs` (`/mnt/pbs-datastore/store`, ext4 on the second virtual disk of VM620 on the 0own hypervisor) holds the backups of all four fleets; when it fills, every fleet's backups fail.

- Alerts: `PBSDatastoreFilesystemHigh` (>80%), `PBSDatastoreFilesystemCritical` (>90%), `PBSDatastoreWillFillWithin5Days` (predict_linear over 2 days) and `PBSDatastoreMetricMissing` live in `config/prometheus/rules/fleet-disk.yml`. They read `node_filesystem_*{mountpoint="/mnt/pbs-datastore"}` from the own-pbs node exporter. Debian's default `--collector.filesystem.mount-points-exclude` hides `/mnt`, so `inventory/fleet-observability.yml` overrides it for `0own_pbs`; without that the series does not exist.
- Growing the disk: `qm resize 620 scsi1 +<n>T` on the 0own hypervisor, then in the guest `growpart /dev/sdb 1 && resize2fs /dev/sdb1` (online). The zvol keeps its 3T refreservation, so the added space is thin-provisioned on `rpool`; keep `zpool list rpool` under 80%.
- Garbage collection runs daily at 05:30 (after the 04:00/04:15/04:30 prune jobs). Chunks younger than 24h5m are never freed, so a GC run right after a backup frees little.
- Prune jobs: `own-pbs-retention` is limited to the root namespace (`max_depth: 0`). A prune job without `max_depth` recurses into every namespace, which used to apply keep-daily 7 to `0database` on top of the tighter `prune-0database` job. `0docker` has its own job; `0mcp-legacy` is frozen and unpruned.

## Fleet loops: pool guardian and horizon (added 2026-10-13)

Two unattended loops run on the 0docker builder (CT108) from systemd timers; both come from the `go_fleet_runner` repository (`docs/architecture/pool-guardian.md`, `docs/architecture/horizon.md`).

- `fleet-pool-guardian.timer` (every 10 minutes) observes the service pools, repairs what is safe and escalates the rest. `fleet-horizon.timer` (every 6 hours) watches what expires or degrades slowly: certificates, the GitHub token, domains, Tailscale keys, RAID, disks, backups.
- Each loop writes a textfile (`/var/lib/prometheus-node-exporter/textfile/fleet_pool_guardian.prom`, `fleet_horizon.prom`) that the builder's node exporter serves; this Prometheus scrapes it through the builder's `tailscale serve` forward on port 9100. The files must be mode 0644: the exporter runs as another user, and `fleet-runner` before v0.7.340 wrote them 0600, which hid both loops from this Prometheus.
- Alerts live in `config/prometheus/rules/fleet-loops.yml`. `*Silent` fires when the heartbeat timestamp is old (guardian 45 minutes, horizon 13 hours). `*NotReporting` fires when the series is absent: a staleness expression returns nothing when the target is down, so without `absent()` a dead builder would silence its own alert. The nightly `ct108-nightly` backup stops the builder for about 10 minutes, which every `for:` outlasts.
- Guardian kept out by the lock (added 2026-10-19): `FleetPoolGuardianSlow` (warning, no finished run for 45 minutes) and `FleetPoolGuardianSilent` (critical, 2 hours) say the guardian has not FINISHED a run, which has two very different causes. A run takes about 20 minutes and never starts while a tool holds the pools lock (`/root/fleet-state/state/pool-guardian/lock`) exclusively: a `deploy-pool`, an `nginx-render` batch such as `/root/rerender_batches.sh`; the timer's tick then says `another run holds the lock; nothing to do` in `journalctl -u fleet-pool-guardian.service` and exits 0 (on 2026-10-19 a batch re-render of 278 pooled vhosts and the deploys queued behind it did that for 2 h 8 min). Since fleet-runner v0.7.672 such a tick writes `fleet_pool_guardian_lock_skip_timestamp_seconds` (`/var/lib/prometheus-node-exporter/textfile/fleet_pool_guardian_lock_skip.prom`), and while that heartbeat is fresh (a tick in the last 75 minutes) `FleetPoolGuardianLockedOut` (warning) fires instead of the critical. The critical comes back when the heartbeat stops (the timer died, or a scan hung on an ssh child) and after 8 hours without a finished run (something holds the lock far too long). To see who holds the lock, on the builder: `ino=$(stat -c %i /root/fleet-state/state/pool-guardian/lock); grep ":$ino " /proc/locks` (the line without an arrow is the holder, the pid is the fifth column; lines with `->` wait), then `ps -o pid,args -p <pid>`. The guardian does not queue behind deploys on purpose (its observation holds the shared lock for a whole scan, which would sit in front of every deploy waiting for the exclusive lock); nothing needs doing unless the holder is stuck.
- `FleetHorizonCriticalFinding` and `FleetPoolGuardianCriticalFinding` repeat what the loops page through their own ntfy topic, as an independent second path. While the 0docker hypervisor runs on one NVMe (four degraded md arrays), `FleetHorizonCriticalFinding` fires; it resolves when the missing disk is replaced and re-added.
- Runner-config drift (added 2026-10-14): `runner-config-drift.timer` (hourly, from fleet-state `systemd/ct108/`) compares the config fleet-runner reads from `/root/fleet-state` (`service-pools.json`, `nginx-upstreams.json`, `builder-pool.json`, `cluster-gateway-upstreams.json`) with master of the private fleet-state repository and writes `fleet_runner_config_drift{file}`. The check also runs right after every successful `fleet-pool-config-mirror` run (every 30 minutes, `OnSuccess=` in the mirror unit, fleet-state #540, 2026-10-22): the hourly phase (:41) always fell a few minutes before the mirror, so while rollouts edit the live pools file all day (the least_conn waves, the keystore wave) the check saw "ahead of git" every time. Compared right after the mirror, drift is an edit made in the last seconds or a mirror that does not work; the hourly timer stays as the fallback for a dead mirror (`journalctl -u fleet-pool-config-mirror.service`). `FleetRunnerConfigDrift` fires when a file has differed for an hour (a standby builder is bootstrapped from git, so a live-only change is lost on failover; found on 2026-10-14: a pool added live and a changed upstream port), `FleetRunnerConfigCheckFailing` when the repository cannot be read for 3 hours, `FleetRunnerConfigCheckSilent` / `FleetRunnerConfigNotReporting` are its dead-man pair. A pool's `weights` counts as runtime state when it has `base_weights`, so pool-balance's capacity adjustments are not drift.
- Pool balance (added 2026-10-14): `fleet-pool-balance.timer` (every 15 minutes) runs `fleet-runner pool-balance`, which turns `pool-plan`'s capacity proposals into weight changes through `nginx-render` (gate: the render may differ in weights only; rollback on any failure; docs/architecture/pool-balance.md in go_fleet_runner). It runs report-only until `FLEET_BALANCE_ARGS="--apply"` is set in `/etc/fleet-runner/pool-balance.env`. Metrics `fleet_pool_balance_*` (`last_run_timestamp_seconds`, `apply_enabled`, `paused`, `pools`, `proposals_pending`, `applied`, `failed`). `FleetPoolBalanceSilent` / `FleetPoolBalanceNotReporting` are the dead-man pair, `FleetPoolBalanceFailed` fires when a change failed or was rolled back. Kill switch: the pool guardian's PAUSE file.
- Triage on the builder: `systemctl status fleet-pool-guardian.timer fleet-horizon.timer`, `journalctl -u fleet-pool-guardian.service -u fleet-horizon.service`, state under `/root/fleet-state/state/pool-guardian/` and `.../horizon/` (`latest.json`, `events.jsonl`). The guardian's kill switch is a `PAUSE` file in its state directory (or `FLEET_GUARDIAN_PAUSE`); the horizon's accepted problems are acknowledged in the `ACK` file there, one per line, each with a mandatory `until=YYYY-MM-DD`.

## Rule files adopted from the live monitoring VM (added 2026-10-14)

Seven rule files were running on the monitoring VM with no copy in git, so a rebuilt VM would have lost them: `fleet-edge-probe.yml`, `node-placement.yml` (placement score, `FleetHostOverloaded`, `FleetHostDiskCritical`, hypervisor memory pressure and `FleetHypervisorContentionMismatch`), `node-thermal-alerts.yml`, `prometheus-capacity.yml`, `pve-host-incident.yml`, `pve-recovery-alerts.yml` and `pve-storage-capacity.yml`. They are now in `config/prometheus/rules/` and shipped by the `monitoring_vm` role (`monitoring_prometheus_adopted_rule_files`, mode 0640 root:prometheus, Prometheus reload on change); the live copies were byte-identical when adopted, except `node-placement.yml`, which carries the fix below (backup `node-placement.yml.bak-pre-mismatch-fix-20261014T0604Z`).

`FleetHypervisorContentionMismatch` matched with a bare `and on()`, so any hot hypervisor made every host under 30% busy alert (26 pending at once when the 0docker hypervisor peaked on 2026-10-14). The only hypervisor series is the 0docker Proxmox host, so the alert now looks only at guests with `fleet="0docker"` (joined through their `instance`). `tests/promtool/node_placement_rules_test.yml` fails on the old expression.

## Boot ordering of the tailnet socket proxies (added 2026-10-13)

A socket unit that is ordered `After=tailscaled.service` forms a cycle with systemd's implicit ordering: every socket is
`Before=sockets.target`, `sockets.target` is before `basic.target`, and `tailscaled.service` starts after `basic.target`.
systemd breaks such a cycle at boot by deleting start jobs. When the 0docker hypervisor was reset on 2026-10-13 it deleted
the start jobs of the tailnet proxy sockets (the node-exporter proxy and the Woodpecker 9000 proxy) and of
`tailscaled.service` itself: the host came up without the tailnet, its metrics were unreachable (`PveHostNodeExporterUnavailable`)
and CI agents could not reach the Woodpecker server until the units were started by hand.

- Fix: socket templates ordered after `tailscaled.service` carry `DefaultDependencies=no` (plus the shutdown conflict that
  default dependencies would have added): `fleet_node_exporter/templates/metrics-proxy.socket.j2` and
  `proxmox_tailscale_proxy/templates/lv3-tailscale-proxy.socket.j2`. `tests/test_fleet_observability_roles.py` pins it.
- Check any host without rebooting it: `systemd-analyze verify default.target 2>&1 | grep -i cycle`. Empty output means
  the boot transaction has no ordering cycle; `Found ordering cycle` lines name the units involved.
- Live state on 2026-10-13: the 0docker hypervisor has the same lines as a drop-in
  (`/etc/systemd/system/<socket>.d/10-no-default-deps.conf`, also for `woodpecker-exec-proxy@.socket`); the check above is
  clean there. A role converge renders the same text into the unit itself; the drop-in is then redundant and harmless.
  The 0mcp hypervisor still showed the cycle before this change (20 `lv3-tailscale-proxy-*` sockets); apply the role or the
  drop-in there before its next reboot.
- Rollback: delete the drop-in (or restore the previous unit text), `systemctl daemon-reload`. Running sockets are not
  restarted by either step.

A second boot-time failure of the same family: an exporter bound to a tailnet address cannot start until `tailscaled`
has the address. The packaged unit (`Restart=on-failure`, 100 ms, 5 starts in 10 s) gave up for good when the 0docker
hypervisor was reset on 2026-10-13, and the nginx guest was no longer scraped (`NodeExporterMissing`).
`fleet_node_exporter` now renders a drop-in (`/etc/systemd/system/prometheus-node-exporter.service.d/10-retry-until-tailnet.conf`:
ordered after `tailscaled.service`, `Restart=always`, `RestartSec=15`, no start limit); switch it off per host with
`fleet_node_exporter_restart_forever: false`. Rollback: delete the drop-in and `systemctl daemon-reload`.

The same check found a second cycle on the 0mcp hypervisor that is not about tailnet sockets: the host control-loop reconcile
path unit (`proxmox_host_control_loops`) is `After=pveproxy.service` and, as a path unit, implicitly `Before=paths.target`;
`pveproxy` is after `ssh.service`, which is after `basic.target`. systemd's way out of that cycle at boot is to delete start
jobs, and `ssh.service` was one of the candidates. The path template now carries `DefaultDependencies=no`; the tailnet proxy
sockets of the 0mcp hypervisor and this path unit have the same fix as drop-ins since 2026-10-13, and
`systemd-analyze verify default.target` is clean there.



## Hypervisor memory, Alertmanager delivery and the monitoring dead-man (added 2026-10-13)

Found in the 2026-10-13 re-audit of the 0mcp fleet; every item was applied live first, then codified.

- **Hypervisor memory.** pve-0mcp read 3% MemAvailable, 99.5% swap, with ~141 GB of guest RAM configured on 128 GB, and nothing
  alerted (`FleetHypervisorMemoryPressure` reads a metric only the 0docker PVE exporter feeds). Rules:
  `config/prometheus/rules/fleet-hypervisor-memory.yml`. Root cause of the apparent exhaustion: memory stranded in
  deferred-split transparent huge pages after ballooning (see the `fleet_hypervisor_memory_reclaim` README); `drop_caches=2`
  returned ~13 GB. pvestatd had already ballooned every guest to its floor (`qm monitor <id>`, `info balloon`: actual == the
  `balloon` minimum), so lowering a floor is the only remaining lever: done for runtime-apps (4096 to 1536 MB) and runtime-ai
  (2048 to 1280 MB), each above max(1.3 x its 7-day peak used, 1 GB). Rollback values are in `/root/balloon-changes-*.txt` on
  the hypervisor. Guests to shrink at the next reboot: runtime-comms (4096 MB, peak used 1.1 GB), nginx (4096 MB, 1 GB),
  0mcp-staging-runtime (8192 MB, balloon disabled), artifact-cache (4096 MB, balloon disabled, peak 0.8 GB).
- **Alertmanager state.** The storage path was root-owned while the unit runs as `prometheus`, so nflog and silences were never
  written. Fixed in the role (PR #356); `AlertmanagerStatePersistenceFailing` now alerts on it.
- **ntfy 413 / 400.** ntfy rejects webhook JSON over its request limit (HTTP 413 `JSON body too large`, observed with 287
  alerts) and implements only a subset of sprig (`int` is not defined: HTTP 400). The receivers send at most
  `alertmanager_runtime_ntfy_max_alerts` (5) alerts; the templates add `.truncatedAlerts` back for the title count and the
  "...and N more" line. Storm routing: `FleetServiceEdgeDown` now joins the family grouped by cluster, job and severity.
- **Load test.** Route `alertname="AlertmanagerLoadTest"` (severity `loadtest`, so fleet-triage skips it) goes to
  `platform-monitoring-warning`. Post 300 alerts with distinct `instance` labels and a 4 minute `endsAt` to
  `http://127.0.0.1:9093/api/v2/alerts` on the monitoring VM; expect one message titled `FIRING (300): AlertmanagerLoadTest +299 more`.
- **Kuma.** Uptime Kuma (runtime-general, `/opt/uptime-kuma`) had no notification channel. A default-enabled `ntfy` channel posts to
  `platform-monitoring-warning` as the publish-only ntfy user `kuma-notify` (password in the fleet vault as
  `kuma-notify-ntfy-password`). It lives in `kuma.db` (not in git). Rollback: stop the container, restore
  `/opt/uptime-kuma/kuma.db.pre-ntfy-notification-<ts>`, start it.
- **Dead-man's switch for the 0mcp monitoring.** CT108 probes the 0mcp Prometheus and Alertmanager every minute over the tailnet and
  the 0docker Prometheus alerts on the result: `baditaflorin/go-fleet-metrics-hub`, `prometheus/rules/mcp-monitoring-deadman.yml`
  and `ops/mcp-monitoring-probe/`.

## CI host pressure alerts

Added 2026-10-26 with the graded Woodpecker admission (services-registry PR 1000/1001). Rules: `config/prometheus/rules/fleet-ci-host-pressure.yml`; unit tests: `tests/promtool/fleet_ci_host_pressure_rules_test.yml`.

| Alert | Fires when | Back-test (7 days) |
| --- | --- | --- |
| `FleetCiHostCpuPressureHigh` | CPU pressure (some task waited for a CPU) over 40% for 30 minutes on `0docker-builder`, `docker-build-lv3`, `0own-build-worker`, `infer-builder-ci` or `0pipe-build` | 2 episodes |
| `FleetCiHostIoPressureHigh` | IO pressure (all tasks stalled) over 50% for 30 minutes on the same hosts | 4 episodes, all on `0own-build-worker` (shared HDD mirror) |
| `FleetCiHostPressureMissing` | fewer than 5 of those hosts report `node_pressure_*` for 15 minutes (a check that reads nothing must not stay green) | not seen |

What to do: the graded load controller (`woodpecker-load-controller@ci.0exec`, `@ci.0mcp` on CT108) should already be closing slots; read its journal for `node_graded` / `agent_graded_closed`, then compare the open slots on ci.0exec.com with the host. If the host is saturated with every slot closed, the load is not CI: look at the guests of its hypervisor (0own: VMs 610, 630, 660 on the 2 HDDs). The infer builder (VM 702) joined on 2026-10-27: node_exporter on its tailnet address `100.64.0.23:9100`, grant `tag:prometheus-monitoring -> tag:infer-builder-ci:9100` in `config/tailscale/policy.hujson`, target in the `infer_node_exporter_via_tailscale` job (`inventory/host_vars/monitoring.yml`). A fifth CI host goes into the three regexes and the count `4` of `FleetCiHostPressureMissing` and its unit test.

## Build host cache trim alerts

Added 2026-11-04. Rules: `config/prometheus/rules/fleet-job-caches-trim.yml`; unit tests: `tests/promtool/fleet_job_caches_trim_rules_test.yml`. Step 3d of the build VM's 4-hourly GC (`docker-build-lv3`, VM 130 on 0mcp; `docker-build-gc.timer` at :23 of hours 0, 4, 8, 12, 16 and 20 UTC) trims the Go build cache inside the `fleet-job-cache-*` Docker volumes to a 20 GiB cap, which is what keeps the VM's root off the disk-full line, and at the end of every full run writes `fleet_job_caches_trim.prom` into node_exporter's textfile directory: `fleet_job_caches_trim_last_run_timestamp_seconds`, `fleet_job_caches_trim_last_result` (0 ran, 1 failed, 2 skipped), `fleet_job_caches_trim_freed_bytes` and `fleet_job_caches_trim_volumes_over_cap`. The 0mcp Prometheus scrapes that node_exporter as `host="docker-build-lv3"`; the 0docker one sees it as `host="0mcp-builder"` and gets no rule.

| Alert | Fires when | Severity |
| --- | --- | --- |
| `FleetJobCachesTrimFailed` | the last full run wrote result 1 or 2 and it stayed for an hour (the file is rewritten by full runs only, so a bad value stays up to 4 hours) | warning |
| `FleetJobCachesTrimStale` | no run has written the file for 9 hours (two missed runs plus slack), for 30 minutes | warning |
| `FleetJobCachesTrimMissing` | no `fleet_job_caches_trim_last_run_timestamp_seconds` series for `docker-build-lv3` for a day (a check that reads nothing must not stay green) | warning |
| `FleetJobCachesOverCap` | a volume still over its cap after every run for 24 hours; above 0 for hours in a CI burst by design, so only a day of it is reported | info (Alertmanager drops it) |

State when written: the rule file is in git only. It is not on the monitoring VM, Prometheus was not reloaded, and the four expressions return nothing on the live Prometheus (three automatic runs on 2026-11-03, all result 0, nothing over the cap), so applying it fires nothing. The file is in `monitoring_prometheus_adopted_rule_files`, so a converge of the `monitoring_vm` role copies it (mode 0640 root:prometheus) and reloads Prometheus; a copy by hand works too (`promtool check rules`, copy to `/etc/prometheus/rules/`, reload). Shipping it is a separate step on the owner's yes.

What to do: for each alert the commands (the journal of `docker-build-gc.service` needs `sudo -n`), the metric file, the kill switch and its effect on `FleetJobCachesTrimStale` are in `config/0mcp/docker-build-lv3/README.md`, section "Alerts on the trim". Where the delays come from, and that they are reasoning checked against less than a day of history, is in the header of the rule file.

## Disk health alerts

Added 2026-10-29 with the 0pipe build server. Rules: `config/prometheus/rules/fleet-disk-health.yml`; unit tests: `tests/promtool/fleet_disk_health_rules_test.yml`. The collector (`proxmox-storage-metrics.timer`, fleet-state `scripts/proxmox-storage-metrics.py`, installed on 0docker, 0mcp, 0infer, 0own and 0pipe with `scripts/install-proxmox-storage-metrics.sh <host> <checkout>`) exports the SMART facts as `fleet_disk_*`; before these rules nothing alerted on them. On the day they were written one 0docker mirror half (`nvme1n1`) had failed SMART at 110% wear and 0pipe's only SSD (a used auction disk) was at 80% wear after 15.7k hours.

| Alert | Fires when | Today (2026-10-29) |
| --- | --- | --- |
| `FleetDiskSmartFailed` (critical) | a drive's SMART overall self-assessment is FAILED for 10 minutes | `0docker/nvme1n1` |
| `FleetDiskWearCritical` (critical) | rated endurance used >= 95% for 1 hour | `0docker/nvme1n1` (110%) |
| `FleetDiskWearHigh` (warning) | rated endurance used 80-94% for 1 hour | `0pipe/sda` (80%) |
| `FleetDiskWearForecast` (warning) | at the 3 day trend the disk reaches 100% within 30 days (disks between 60 and 100% only) for 6 hours | none yet (needs 3 days of 0pipe data) |
| `FleetDiskBadSectors` (warning) | a reallocated, pending, offline-uncorrectable or media-error counter is above 0 for 30 minutes | none: every such counter was 0 fleet-wide |
| `FleetDiskHot` (warning) | a disk above 65 C for 30 minutes (fleet disks run at 31-52 C) | none |
| `FleetDiskHealthMissing` (warning) | fewer than 5 hosts report `fleet_disk_smart_passed` for 30 minutes (a check that reads nothing must not stay green) | none |

What to do: SMART failed or wear critical on a mirror: replace the drive before the other half follows (check `mdadm --detail`, then the vendor's replacement). On 0pipe (single SATA SSD, no RAID, nothing unique on it) a failing disk means rebuilding the host from the private repo `baditaflorin/0pipe` and moving the Woodpecker agents; open a Hetzner support ticket with the `smartctl -a` output to ask for a drive swap while the disk still works. To see what writes to a disk: `node_disk_written_bytes_total{device="sda"}` per host in Prometheus.

## Docker network pool alerts

Added 2026-10-29. Rules: `config/prometheus/rules/fleet-docker-networks.yml`; unit tests: `tests/promtool/fleet_docker_networks_rules_test.yml`. The numbers come from fleet-state `scripts/docker-network-gc.py`, a systemd timer (every 30 minutes) on every Docker host in fleet-state `scripts/docker-network-gc.hosts`, installed and checked with fleet-state `scripts/install-docker-network-gc.sh install|status --all`.

Why: each bridge network takes one subnet from the Docker daemon's `default-address-pools`. Docker's built-in pools hold 31; the fleet's usual `daemon.json` pools (172.16.0.0/12, 192.168.0.0/16, 10.200.0.0/16 cut into /24s) hold about 4,600. A Woodpecker agent that loses its Docker socket or is killed leaves its per-workflow network `wp_<ulid>_<n>_default` behind; on 2026-10-28 these filled infer-builder-ci and every workflow on agent 110 failed with "could not find an available, non-overlapping IPv4 address pool among the defaults". The timer removes a network only when its name matches `^wp_[0-9a-z]+_[0-9]+_default$`, no container is attached and it is older than 6 hours (Woodpecker's longest pipeline timeout is 2 h). It never runs `docker network prune`, which would also take a workflow's network before its first container exists and every stopped compose project's network.

| Alert | Fires when |
| --- | --- |
| `DockerNetworkPoolNearlyFull` | fewer than 5 pool subnets left on a host for 5 minutes |
| `DockerNetworkPoolExhausted` (critical) | no pool subnet left for 1 minute: every new network on that host fails |
| `DockerNetworkGcStale` | the timer has not completed a run on a host for 3 hours |
| `DockerNetworkGcHostsMissing` / `DockerNetworkGcHostsMissingNone` | fewer than 21 scraped Docker hosts report the metrics, or none at all, for 30 minutes |

What to do: on the host, `docker network ls --filter name=wp_` and `docker network inspect -f '{{.Name}} {{.Created}} {{len .Containers}}'` on them; leaked networks younger than 6 hours come in bursts (about 15 within 20 minutes when an agent lost its socket on 2026-10-28) and can be removed by hand once no container is attached and the agent that created them has been restarted. The lasting fix for a host on the built-in 31 is larger `default-address-pools` in `/etc/docker/daemon.json`, which needs a dockerd restart: drain the host's agents in the load controller first. Metrics per host: `docker_network_pool_capacity_subnets`, `docker_network_pool_used_subnets`, `docker_network_pool_configured`, `docker_networks_total`, `woodpecker_leaked_networks`, `woodpecker_leaked_networks_removed_total`, `docker_network_gc_last_success_timestamp_seconds`. infer-runtime and 0mcp-staging-runtime run the timer but have no node_exporter scrape target, so their numbers reach no alert yet; coolify-apps-lv3 does not run it (its node_exporter is a `prom/node-exporter` container with no textfile mount; 4,608-subnet pools, no Woodpecker agent). A newly scraped Docker host goes into the count `21` of `DockerNetworkGcHostsMissing` and its unit test.

## CI cache prune alerts

Added 2026-11-02. Rules: `config/prometheus/rules/fleet-ci-cache-prune.yml`; unit tests: `tests/promtool/fleet_ci_cache_prune_rules_test.yml`. The host-local Go/npm CI cache of the Woodpecker pilot agent `0own-build-worker` (VM 610; services-registry PR #806 and its runbook `docs/runbooks/woodpecker-ci-go-cache-pilot.md`) is trimmed by `woodpecker-ci-cache-prune.timer` at about 03:15 UTC. From 2026-10-21 to 11-01 `go-build` ended every run above its 8 GB cap (14 to 27 GB) and nothing alerted: `prune.sh` logged a line and exited 0. It now exits 3 in that case and, with `--prom /var/lib/prometheus/node-exporter/ci-cache-prune.prom`, writes the textfile these rules read: `ci_cache_prune_size_bytes`, `ci_cache_prune_cap_bytes` and `ci_cache_prune_over_cap` per `cache` (`go-build`, `go-mod`, `npm`) and `ci_cache_prune_last_run_timestamp_seconds`. That host's second node-exporter (`100.88.44.116:9101`, textfile directory `/var/lib/prometheus/node-exporter`) is already scraped through the Scanopy `file_sd` list with `host="0own-build-worker"` (read on the monitoring VM, 2026-11-02).

| Alert | Fires when |
| --- | --- |
| `CiCacheOverCap` | a cache is still over its cap after the nightly run deleted everything it may, for 5 minutes (the flag is written by that run, so it stays 1 until the next run) |
| `CiCachePruneStale` | no run has finished for 36 hours (30 minute wait) |
| `CiCachePruneMissing` | no `ci_cache_prune_*` series at all for 3 days (a check that reads nothing must not stay green) |

State when written: the new `prune.sh` is not on the pilot host yet and the pilot PR is not merged, so there are no series; the first two rules stay quiet and `CiCachePruneMissing` would speak after 3 days. The file is in `monitoring_prometheus_adopted_rule_files`, so a converge of the `monitoring_vm` role copies it (mode 0640 root:prometheus) and reloads Prometheus; a copy by hand works too (`promtool check rules`, copy to `/etc/prometheus/rules/`, reload).

What to do: `CiCacheOverCap`: on the host read `journalctl -u woodpecker-ci-cache-prune.service --since -2d`; its `ALERT` line names the cache. Either one working day needs more than the cap (`go-build` measured 14 to 27 GB per working day in 11-2026): raise the flag in the unit's drop-in `/etc/systemd/system/woodpecker-ci-cache-prune.service.d/caps.conf` (an empty `ExecStart=` line, then the full command), `systemctl daemon-reload`; or something other than the pipelines writes into `/var/cache/woodpecker-ci` (`du -sh` of the three directories, newest files first). `CiCachePruneStale` and `CiCachePruneMissing`: `systemctl status woodpecker-ci-cache-prune.timer woodpecker-ci-cache-prune.service`, then `ls -l /var/lib/prometheus/node-exporter/ci-cache-prune.prom` and `curl -s http://100.88.44.116:9101/metrics | grep ci_cache_prune`. A second agent host that gets the host-local cache needs no change here: its series carry its own `host` label.

## Woodpecker agent record alerts

Added 2026-10-29. Rules: `config/prometheus/rules/fleet-woodpecker-agent-records.yml`; unit tests: `tests/promtool/fleet_woodpecker_agent_records_rules_test.yml`. On 2026-10-28 eight agent records on ci.0exec lost their name (a `PATCH /api/agents/{id}` without `name` stores an empty one; labels survive), the CT108 load controller logged `node_missing` ~1,500 times per node and managed no infer, 0own or 0mcp slot for about a day, and nothing alerted. The metrics come from services-registry `bin/woodpecker_agent_names_check.py`, run every minute by `woodpecker-agent-names-check.timer` on CT108 (textfile `woodpecker-agent-names.prom`).

| Alert | Fires when | Fix |
| --- | --- | --- |
| `WoodpeckerAgentRecordUnnamed` | an agent record has an empty name for 10 minutes | restart the idle agent (`GET /api/agents/<id>/tasks` empty first); it re-registers `WOODPECKER_HOSTNAME` |
| `WoodpeckerControllerNodeMissingAgents` | a controller config node lists names no agent has, for 10 minutes | as above, or remove the stale name from `/etc/woodpecker-load-controller/<plane>.json` (backup first) |
| `WoodpeckerAgentNamesBeingWiped` | the check restored an emptied name in the last 15 minutes (a caller PATCHes agents without `name`) | the wipe is already undone; find the caller (nginx access log on VM104, `PATCH /api/agents`, user agent) and make it send `name` and `no_schedule` |
| `WoodpeckerAgentRecordCheckBlind` | the check cannot read a plane, or its series is absent, for 15 minutes | check the timer and the plane's API token on CT108 |

Every script that PATCHes an agent must send `name` and `no_schedule` (a body without `name` stores an empty name). Since 2026-10-30 the check runs with `--repair` and restores a wiped name within a minute (state `/var/lib/woodpecker-agent-names/state.json` on CT108), so the alert above is the only trace of the caller.

## Woodpecker exporter alerts

Added 2026-10-30. Rules: `config/prometheus/rules/fleet-woodpecker-exporter.yml`; unit tests: `tests/promtool/fleet_woodpecker_exporter_rules_test.yml`. The exporter is the private repo `baditaflorin/fleet-woodpecker-metrics` (script, units, `scripts/install.sh`, `scripts/check-drift.sh`), run every five minutes by `fleet-woodpecker-metrics.timer` on CT108, textfile `woodpecker.prom`.

- `WoodpeckerControlPlaneUnreachable` (warning, 10 m): `woodpecker_control_plane_up` is 0 for a plane. The exporter's API call failed: the server is down, the token file is unreadable, or the private proxy is. Check `curl` against the plane from CT108 and `systemctl show fleet-woodpecker-metrics.service -p Result`.
- `WoodpeckerExporterMissing` (warning, 15 m): the series is gone: the timer is stopped or every run fails. `systemctl status fleet-woodpecker-metrics.service` and `journalctl -u fleet-woodpecker-metrics` on CT108; if the script changed, `scripts/check-drift.sh` and roll back with the `.bak-<UTC>` copy.

## Hypervisor log shipping alerts

Added 2026-11-01. Rules: `config/prometheus/rules/fleet-log-shipping.yml`; unit tests: `tests/promtool/fleet_log_shipping_rules_test.yml`. Until 2026-10-30 the 0mcp, 0infer and 0pipe hypervisors sent nothing to OpenObserve `host_logs` (only the build VM and the guests shipped) and nothing noticed. The metrics come from `config/0own/openobserve/log-freshness/openobserve-log-freshness.py`, run every 2 minutes by `openobserve-log-freshness.timer` on VM 630 (textfile `openobserve-log-freshness.prom`); the host list is the `HYPERVISORS` constant in the script, so a new hypervisor shipper must be added there.

| Alert | Fires when | Fix |
| --- | --- | --- |
| `HypervisorLogShippingSilent` | a listed hypervisor has no event in `host_logs` for over 2 hours (a host not seen in the 6 h window counts as silent), for 10 minutes | `systemctl status vector` and `journalctl -u vector` on the host; reinstall with 0pipe `scripts/install-vector-host.sh <alias> <label>`. 0mcp once kept its live journal in `/run` (tmpfs): `journalctl --flush` |
| `LogFreshnessProbeBlind` | the probe cannot query OpenObserve, or its series is absent, for 15 minutes | `systemctl status openobserve-log-freshness.timer` and `journalctl -u openobserve-log-freshness` on VM 630 (`ssh 0own_openobserve`); OpenObserve on 127.0.0.1:5080 |

The probe never reports hosts silent when it could not read: a failed query writes only `openobserve_log_freshness_up 0`.

The timestamp's hypervisor identity is `shipper_host`. The collector itself is
a guest, so its scrape target supplies its own `host` and `role="guest"`.
Do not select these timestamps with `role="hypervisor"` or group them by the
collector's `host`: that loses the hypervisors despite a healthy probe. The
2026-11-07 exact-main replay verified five fresh per-shipper age series and
both loaded rules healthy after a main-process reload; see the
[live-apply receipt](../../receipts/live-applies/2026-11-07-log-shipping-labels-live-apply.json).
