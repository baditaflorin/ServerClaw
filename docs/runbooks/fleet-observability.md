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
| 0mcp hypervisor build-metrics proxy `woodpecker-0exec-build-metrics-proxy.{socket,service}`: tailnet `203.0.113.6:9103` (`FreeBind=true`) to `10.10.10.30:9100` (docker-build VM exporter); consumer CT108 `100.114.37.21` | `fleet_node_exporter` | `fleet_node_exporter_socket_proxies` (`free_bind: true`, `consumer`, `consumer_grants`) |
| 0docker hypervisor stale `woodpecker-exec-proxy@9100.socket`: kept stopped and disabled (`state: disabled`) | `fleet_node_exporter` | `fleet_node_exporter_socket_proxies` |
| PVE host firewall line `100.114.37.21/32 -> 203.0.113.6 tcp 9103` on the 0mcp hypervisor | `proxmox_security` (`host.fw.j2`) | `proxmox_host_additional_tcp_rules` in `inventory/host_vars/proxmox-host.yml` |
| Tailnet grant `tag:builder-metrics-controller -> 203.0.113.6/32 tcp:9103` and its policy test | `config/tailscale/policy.hujson` | applied with `scripts/tailscale_policy_sync.py` (see `docs/runbooks/tailscale-metrics-grants.md`) |
| CT108 `tailscale serve --tcp=9100` to the internal exporter | `fleet_node_exporter` | `fleet_node_exporter_tailscale_serve_tcp` |
| github-mirror nftables (tcp 9100 only from the monitoring VM on `tailscale0`) | `fleet_guest_firewall` | `fleet_guest_firewall_allowed_inbound` |
| Advertised subnet routes (0docker hypervisor `.109/32`, 0own hypervisor `.50/32`, plus the pre-existing ones) | `fleet_tailscale_node` | `fleet_tailscale_node_advertise_routes` |
| vzdump metrics hook, PBS storage `own-pbs-0database` (non-secret fields), job `pg-primary-daily-pbs` (VM 100, snapshot, 02:30, bwlimit 100000 KiB/s) | `fleet_pg_backup` (`pve_backup`) | `fleet_pg_backup_pve_*` |
| `/etc/pgbackrest` layout, `pgbackrest.conf`, `pgbackrest-daily`, prepared (not installed) service and timer | `fleet_pg_backup` (`pgbackrest`) | `fleet_pg_backup_pgbackrest_*` |
| own-pbs realm user, ACLs on the `0database` namespace, prune job `prune-0database` | `fleet_pg_backup` (`pbs_server`) | `fleet_pg_backup_pbs_*` |
| `fleet-docker-prune` script, service and daily timer (04:30 UTC, unused images and BuildKit cache older than 7 days; textfile metrics `fleet_docker_prune_*`) on the 0mcp docker-build guest | `fleet_docker_prune` | `fleet_docker_prune_*`; host `0mcp_docker_build` in group `fleet_docker_prune_hosts` |
| Root-filesystem alerts (`FleetRootFilesystemLow` <15% free 30m, `FleetRootFilesystemCritical` <7% 10m, `FleetRootFilesystemFillingFast` predicted full within 24h) and `FleetDockerPruneStale` | `monitoring_vm` | `config/prometheus/rules/fleet-disk.yml` (copied to `/etc/prometheus/rules/fleet-disk.yml` on the monitoring VM) |
| Dead-man and finding alerts for the pool guardian and horizon loops on the 0docker builder (`FleetPoolGuardianSilent`, `FleetPoolGuardianNotReporting`, `FleetPoolGuardianCriticalFinding`, `FleetPoolGuardianCircuitOpen`, `FleetPoolGuardianPaused`, `FleetHorizonSilent`, `FleetHorizonNotReporting`, `FleetHorizonCriticalFinding`) | `monitoring_vm` | `config/prometheus/rules/fleet-loops.yml` (copied to `/etc/prometheus/rules/fleet-loops.yml` on the monitoring VM) |
| the nginx guest's tcp 9100 rule | already in PR #299: `network_policy.guests.nginx` rendered by `linux_guest_firewall` | `inventory/host_vars/proxmox-host.yml` |

### Docker prune and disk alerts

Why: a Woodpecker `test` step on the docker-build guest (VM 130) failed with `no space left on device` while compiling
Go (`/tmp/go-build...` is in the step container's writable layer under `/var/lib/docker` on `/`). Nothing pruned the
host and `/` stood at 83% with 91 images (two 2.4 GB Playwright images among them).

- The timer removes only unused images and old build cache; it does not touch containers, volumes or networks.
- The alert rules apply to every host the 0mcp Prometheus scrapes with `mountpoint="/"`. That includes docker-build
  (`10.10.10.30`), Builder CT108 (`100.114.37.21`) and the 0docker hypervisor (`203.0.113.5`), which it reaches over
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
   The tailnet grant `tag:builder-metrics-controller -> 203.0.113.6/32 tcp:9100` and the cluster firewall rule
   `100.114.37.21/32` tcp 9100 were removed from the live tailnet policy, `config/tailscale/policy.hujson` and
   `proxmox_cluster_additional_tcp_rules`. Nothing used them. The monitoring VM keeps `tag:prometheus-monitoring ->
   203.0.113.6/32 tcp:9100`.
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
   -> tailnet grant  tag:builder-metrics-controller -> 203.0.113.6/32 tcp:9103
   -> PVE host.fw    IN ACCEPT -source 100.114.37.21/32 -dest 203.0.113.6 -p tcp -dport 9103
   -> woodpecker-0exec-build-metrics-proxy.socket  ListenStream=203.0.113.6:9103  FreeBind=true
   -> systemd-socket-proxyd 10.10.10.30:9100  (docker-build VM130 node_exporter, nodename=docker-build)
```

Port plan of the tailnet address `203.0.113.6`: `:9100` hypervisor exporter, `:9101` runtime-general proxy, `:9102`
hypervisor exporter, `:9103` build-metrics proxy.

Why `FreeBind=true`: a socket unit binds its address when it starts. When tailscaled restarts, `tailscale0` can briefly
have no `100.x` address and the bind fails with `Cannot assign requested address`; that is what killed the proxy on
2026-10-11 00:53 and left it dead until someone noticed. `FreeBind=true` (`IP_FREEBIND`) lets the socket bind an
address that is not (yet) assigned, so it keeps listening across the restart and the connection works as soon as the
address is back.

Checks (read-only):

```sh
ssh operator-bastion 'systemctl show -p FreeBind -p Listen woodpecker-0exec-build-metrics-proxy.socket; ss -ltn | grep :9103'
ssh 0docker_bastion 'pct exec 108 -- bash -lc "curl -s --socks5-hostname 127.0.0.1:1055 http://203.0.113.6:9103/metrics | grep -m1 ^node_uname_info"'   # nodename="docker-build"
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
| Disk alert rules | delete `/etc/prometheus/rules/fleet-disk.yml` on the monitoring VM and reload Prometheus |
| Fleet loops rules | delete `/etc/prometheus/rules/fleet-loops.yml` on the monitoring VM and reload Prometheus |
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
- `FleetHorizonCriticalFinding` and `FleetPoolGuardianCriticalFinding` repeat what the loops page through their own ntfy topic, as an independent second path. While the 0docker hypervisor runs on one NVMe (four degraded md arrays), `FleetHorizonCriticalFinding` fires; it resolves when the missing disk is replaced and re-added.
- Triage on the builder: `systemctl status fleet-pool-guardian.timer fleet-horizon.timer`, `journalctl -u fleet-pool-guardian.service -u fleet-horizon.service`, state under `/root/fleet-state/state/pool-guardian/` and `.../horizon/` (`latest.json`, `events.jsonl`). The guardian's kill switch is a `PAUSE` file in its state directory (or `FLEET_GUARDIAN_PAUSE`); the horizon's accepted problems are acknowledged in the `ACK` file there, one per line, each with a mandatory `until=YYYY-MM-DD`.
