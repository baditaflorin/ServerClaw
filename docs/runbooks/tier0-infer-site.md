# Tier-0 standby site on 0infer (infer-tier0, VM704)

Purpose: a second alert stack and a warm vault/keystore standby on a host that fails independently of 0mcp and 0docker.
Extends `tier0-replication.md` (encrypted snapshots to 0mcp/0own, key escrow) and `fleet-state` `docs/tier0-multihost-design.md`; it does not replace
them. Design and history: `RESILIENCE-TIER0-ON-0INFER.md` (claude_team).

## What runs where
| Piece | Where | Notes |
|---|---|---|
| VM704 `infer-tier0` | 0infer Proxmox host, `10.70.10.40`, 4 vCPU / 8 GB, onboot | Not a tailnet node (no unattended join path: the policy OAuth client has no `auth_keys` scope). Reached through the 0infer host (`100.64.0.21`), see below |
| Alertmanager #2 (v0.28.1, same as the primary) | VM704 `/opt/tier0/alertstack` | Gossip mesh with the primary; config generated from the primary's live file by `gen-alertmanager.py` |
| ntfy #2 | VM704, public `https://alerts.example.org` (Caddy, Let's Encrypt) | Random readable topics (`t0-crit-*`, `t0-warn-*`, `t0-wd-*`); phone subscribes once via an `ntfy://` link |
| Vault + keystore warm standby | VM704 `/opt/tier0/vault-standby`, **stopped** until promoted | Fed by the courier on CT108 every 2 min (`vault-standby-send.timer`) |
| nft DNAT/SNAT | 0infer host `/etc/nftables/infer-tier0-ingress.nft` | Public 80/443 -> VM704; tailnet-side 9093/9094 (tcp+udp), 2586, 9101 (-> VM 9100), 2240 (-> VM 22); VM704 outbound to the tailnet is source-NATed to the host |
| DNS | `alerts.example.org` A 203.0.113.20 (Hetzner Cloud DNS zone example.org) | TTL 300 |

## Network path (why the 0infer host is in the middle)
Tailnet grants (config/tailscale/policy.hujson, #407/#408): monitoring VM -> `100.64.0.21` tcp 9093/9094/2586/9101 + udp 9094; `100.64.0.21` -> monitoring VM
tcp 9090/9093/9094 + udp 9094; Builder CT108 -> `100.64.0.21` tcp 2240. Guest firewall on the monitoring VM: `inventory/host_vars/proxmox-host.yml`
`network_policy.guests.monitoring` (#409; applied live with `nft add rule`, never reload the whole file: `flush ruleset` would drop Docker/Tailscale rules).
CT108 runs tailscaled in userspace mode, so its ssh to the host uses `ProxyCommand=nc -X connect -x 127.0.0.1:1056`.

## Live-only changes on monitoring-lv3 (timestamped backups next to each file)
1. `/etc/default/prometheus-alertmanager` ARGS += `--cluster.advertise-address=100.64.0.4:9094 --cluster.peer=100.64.0.21:9094` (backup `.bak-pre-tier0-cluster-*`).
2. `/etc/alertmanager/alertmanager.yml`: one extra webhook after each existing `ntfy-critical|warning|watchdog` webhook, same template/query, URL
   `http://100.64.0.21:2586/<t0 topic>`, bearer file `/etc/alertmanager/ntfy-tier0-token` (backup `.bak-pre-tier0-fanout-*`). The fleet-triage receiver and the
   live ntfy templates are untouched.
3. `/etc/prometheus/prometheus.yml`: second alertmanager target `100.64.0.21:9093`; scrape jobs `tier0_node_exporter` (`100.64.0.21:9101`) and
   `alertmanager_tier0` (`100.64.0.21:9093`) (backups `.bak-pre-tier0-am2-*`, `.bak-pre-tier0-scrape-*`).
4. Rules: `config/prometheus/rules/tier0-standby.yml` (this PR) -> `/etc/prometheus/rules/tier0-standby.yml` (root:prometheus 0640). Reload: `promtool check config`
   then `systemctl kill -s HUP 0mcp-prometheus.service`.
Rollback: copy the backup back, `systemctl reload prometheus-alertmanager` (or restart for the ARGS change) / HUP Prometheus. These files are not yet rendered by the
`alertmanager_runtime` / `monitoring_prometheus` roles: a role run would drop items 1-3 until they are templated.

## Vault standby (what it is, and how it differs from tier0-replication.md)
- Courier `/usr/local/sbin/vault-standby-send` on CT108 (source: `config/0infer/tier0-vault-standby/ct108-courier/`): `sqlite3 .backup` on VM100 (busy timeout + retries), gzip, ssh to `vsync@100.64.0.21:2240`
  (key `/root/.ssh/tier0_sync`, authorized on VM704 with `command="/usr/local/bin/vault-standby-receive",restrict`); the receiver only accepts `put secrets|keystore`,
  integrity-checks, rejects empty DBs, swaps atomically, keeps 6 copies, drops stale WAL/SHM. Metric `vault_standby_sync_*` (textfile).
- **Unlike the encrypted replicas, VM704 holds `SECRETS_MASTER_KEY`, `SECRETS_ADMIN_TOKEN` and the keystore admin token in `/opt/tier0/vault-standby/.env` (root 0600)** so it can
  serve without a human. This was an explicit operator decision (2026-10-14: fully unattended). The data copy is encrypted-at-rest by the vault; the .env is not. Treat VM704
  as tier-0 (single purpose, key-only ssh, no tenants) and keep it in the PBS namespace `0infer`.
- Promotion drill (2026-10-14): `promote.sh` started keystore + vault from the replicated copy; a one-use infra-privileged key from the standby keystore read
  `GET /secrets` = 1041 records, equal to the primary. Promotion does NOT move DNS or gateway upstreams; that is a separate deliberate step.
- Open: epoch/fencing (design §3.2) is not implemented here; never run primary and standby as writers at the same time. One piece exists since 2026-10-17: the courier's receiver refuses uploads while the standby runs (see "Files in git"). It protects this courier-fed copy only: the automated failover (`tier0-failover.sh --promote`) promotes the vault on the 0mcp standby host from the encrypted replicas and never writes `/opt/tier0/vault-standby`.

## Alerts (`tier0-standby.yml`)
`VaultStandbySyncStale|VeryStale|Missing`, `AlertmanagerMeshDegraded` (members < 2), `Tier0SiteDown`, `Tier0SiteAlertmanagerDown`.

## Backups
PBS namespace `0infer` (`own-pbs-0infer`): `infer-tier0-nightly-pbs` (VM704, 02:30), `infer-guests-nightly-pbs` (701-703, 03:00, bwlimit 300 MiB/s), host config via
`host-config-backup@own-pbs-0infer.timer`; prune job `prune-0infer` (keep-last 3, keep-weekly 1, 04:50).

## Second Proxmox Backup Server (PBS #2) on VM704, added 2026-10-15
Purpose: a second copy of the critical backups on a different host and disk than PBS #1 (VM 620 on 0own, whose 4 TB datastore disk is excluded from its own backups).
- Datastore `tier0` at `/srv/pbs-datastore` on a dedicated 800 GB LV (`infer-pg-data:vm-704-disk-0`, **`backup=0`**: never back it up into PBS #1). Same PBS version as PBS #1 (4.2.8).
  GC daily 07:30 UTC, prune job `prune-tier0` (keep-last 3, keep-weekly 1, 07:00 UTC). No web login is configured; administer with `proxmox-backup-manager` as root on VM704.
- Per-group retention (2026-10-17): `pbs-group-retention.timer` (07:05 UTC, after `prune-tier0`) keeps `0docker:vm/100` and `0database:vm/100` at their newest 2 snapshots (the two churny groups; the second copy needs less depth), guarded and dry-run by default; see `config/0infer/tier0-pbs2/README.md`.
- Pull sync from PBS #1 (remote `own-pbs`, read-only user `pbs-sync-0infer@pbs`, token `pull`, DatastoreReader on `/datastore/own-pbs`): jobs `pull-0docker`, `pull-0database`, `pull-0infer` (excludes vm/701),
  `pull-0own` (excludes vm/610), `pull-0mcp-critical` (root namespace, groups vm/100, 110, 140, 150, 152, 154), daily 08:00 UTC, `transfer-last 2`, `remove-vanished false`.
  Path: VM704 -> 0infer host (nft forward + masquerade, rule tagged "PBS#2 pull-sync") -> tailnet grant 100.64.0.21 -> 100.64.0.11 tcp 8007 (#407).
- Not synced on purpose (rebuildable or empty): 0own vm/610 (build worker), 0infer vm/701, 0mcp vm/130, 120, 171, 180 and the legacy namespace. Add groups by editing the jobs' group-filter; check `df /srv/pbs-datastore` first.
- Second independent watchdog on VM704 (`fleet-watchdog.timer`): host SSH key pins, ntfy #1 health, TCP reachability of PBS #1 :8007, PBS #2 freshness and fullness; alerts go to BOTH ntfy servers.
  `must_exist` is empty until the first full sync completes (then restore it from `resilience/watchdog/config.tier0.must_exist.json`).
- Capacity facts (2026-10-15): PBS #1 referenced data 2.59 TB, on disk 3.55 TB; ~900 GB were freed by an external prune of the `0mcp-legacy` namespace and are reclaimed by GC after the atime grace (about two GC cycles); watch `PBSDatastoreFilesystemHigh`.

## Weekly vault standby promotion drill (added 2026-10-15)
`vault-standby-drill.timer` on infer-tier0 (Sat 04:20 UTC): starts the standby keystore + vault (bound to 127.0.0.1 only), issues a one-use infra-privileged key from the
standby keystore, lists secrets through the standby vault, sanity-checks the record count against the previous drill (fails on a drop of more than 15%, or fewer than
100 records), requires both replicated copies to be younger than 15 minutes, then stops everything again and verifies nothing is left running. It prints and writes no secrets.
**Guard:** if the standby is already running (a real promotion) the drill refuses to touch it and only reports `vault_standby_drill_skipped 1`.
Metrics `vault_standby_drill_*` (textfile, scraped through job `tier0_node_exporter`); alerts `VaultStandbyDrillFailed`, `VaultStandbyDrillStale` (> 9 days) and
`VaultStandbyRunning` (critical, skipped for 30 minutes: possible second writer) in `config/prometheus/rules/tier0-standby.yml`. Tested 2026-10-15: pass (1180 records, 9 s),
skip when the standby was running (containers left untouched), fail on a stale copy.

**Files in git (2026-10-17).** `config/0infer/tier0-vault-standby/` holds `compose.yml`, `drill.sh`, `drill_check.py`, `promote.sh`, the courier receiver
`vault-standby-receive` and the drill units, copied byte-identical from VM704; its README has the live paths, owners/modes and the install, rollback and rebuild steps.
The courier sender and its units are in the `ct108-courier/` subdirectory (copied from CT108, same README, tests in `tests/test_tier0_vault_standby_courier.py`); its private key `/root/.ssh/tier0_sync` and `known_hosts_tier0` stay on CT108 only. **The receiver refuses uploads while the standby runs** (exit 5, nothing written, upload drained; it probes the standby's ports 18021/18140, see the README), so a push never swaps the database under a running standby (the weekly drill, `tier0-secret` reads, a manual `promote.sh`). Only a manual `promote.sh` on VM704 makes this copy a writer, and then the guard holds only while the containers run: before stopping a manually promoted standby copy its writes back to the primary or stop `vault-standby-send.timer` on CT108 first.
`.env` (secrets) and `data/` stay on the host only. Change a file there by PR, then install it with a dated `.bak-<date>` backup. Two `drill.sh` bugs were fixed in the
same change: cleanup now polls up to ~20 s for the containers to stop (see below), and a FAILED drill now replaces the `.prom` file. Before, a failure wrote only
`vault_standby_drill.prom.tmp`, so Prometheus kept the previous PASS and `VaultStandbyDrillFailed` could not fire (only `VaultStandbyDrillStale`, after 9 days).
`tests/test_tier0_vault_standby_drill.py` runs the drill against stub commands.

**Standby images.** `/opt/tier0/vault-standby/compose.yml` is not managed by fleet-runner; its source is `config/0infer/tier0-vault-standby/compose.yml`, so bump the pin there by PR too. When the production keystore or vault schema moves on, bump the standby too, or the next drill (or a real promotion) runs old code on a newer copy:
1. `docker save` the image on the dockerhost, then `sudo docker load` it on VM704.
2. Back up `compose.yml` as `compose.yml.bak-pre-<version>-<date>`, then edit the image tag.
3. Run `sudo systemctl start vault-standby-drill.service` as the test. If it fails, restore the backup and run the drill again.

Current pins (2026-10-17): keystore `apikey-service:a6bad2e` (0.7.5) and vault `go-fleet-secrets:289c536` (0.7.3). The drill passed (1240 records, 11 s). One earlier run that day failed only its post-stop check, "standby containers still running after the drill", while both containers exited cleanly about a second later: a race in `drill.sh` cleanup, fixed 2026-10-17 (it polls the running count for up to ~20 s before failing). History: keystore `f7075a9` and vault `f6b2927` on 2026-10-16, `aac2153` and `23fcdd5` before that.
The keystore copy the courier ships now carries the production node's keystore-mesh tables. That is harmless with the mesh off; turning the standby into a live mesh replica would replace the courier for the keystore and needs `promote.sh` and the drill reworked.

## Weekly cross-host restore drill from the second PBS (added 2026-10-15)
`xhost-restore-drill.timer` on the 0infer host (Sun 06:30 UTC, `/usr/local/sbin/xhost-restore-drill`, config `/etc/xhost-restore-drill/config`) restores the newest backup of one guest per ISO week
(rotating `tier0-pbs-0own:670`, `tier0-pbs-0database:103`) from PBS #2 onto directory storage `local` of the 0infer host, i.e. a different host and storage type than where it was backed up. The scratch VM (id 9000+vmid)
gets NO NIC (verified before start), 1 GB RAM, boots, and when it has a guest agent the drill reads `/etc/os-release` and the hostname through it (file-level proof); without an agent it requires boot activity
(uptime >= 60 s and >= 50 MB read). It is then destroyed and the drill verifies no VM, files or LVs remain. Guards: scratch id must not exist, MemAvailable >= guest RAM + 3 GB, >= 80 GB free on the target.
PVE storages on the 0infer host: `tier0-pbs`, `tier0-pbs-0own`, `tier0-pbs-0database` (read-only token `restore-drill@pbs!t` on PBS #2, DatastoreReader). Metrics `xhost_restore_drill_*` (textfile; scraped by job `infer_node_exporter_via_tailscale`);
alerts `XhostRestoreDrillFailed`, `XhostRestoreDrillStale` (> 9 days). Tested 2026-10-15: 0own vm/670 PASS (8 s restore, agent answered "Debian GNU/Linux 13 (trixie)"), 0database vm/103 PASS (7 s restore, boot activity).

## Role-run parity gate (added 2026-10-16)
Before ANY run of the `monitoring_vm` or `alertmanager_runtime` roles against the monitoring VM, run `scripts/monitoring_live_parity.py --live-dir <dir>` (the module docstring has the four `ssh ... sudo cat` commands that fill `<dir>`).
It renders what the repo would deploy and compares it with the live files; exit 0 means a run changes nothing material in: every Prometheus scrape job and the alerting/global/rule_files blocks, the Alertmanager config (route, receivers, inhibit rules) and its ARGS file, and every adopted rule file byte-for-byte.
Two inputs legitimately live outside git and are read from the live file instead: the primary ntfy base URL (service topology) and the secondary ntfy topic names (anonymously readable, never committed). If the inventory enables the secondary ntfy but a live receiver lacks it, that is reported as a difference.
`tests/test_monitoring_live_parity.py` proves the gate also FAILS on removed/added/changed scrape jobs, an altered alerting block, a dropped ntfy fan-out, a changed route, ARGS drift and a missing or edited adopted rule file.
Status 2026-10-16 (checked against the live VM): **PARITY OK** for all of the above, 23 scrape jobs and 23 live rule files (all in the adopted list or generated at apply time).

Deliberately NOT covered, and why a role run is still not a free action for them:
- `https_tls_alerts.yml`, `https_tls_targets.yml` and the SLO files are generated at live-apply time from the probe catalog (scripts/generate_https_tls_assurance.py, materialize_live_apply_worktree_artifacts.py); they are not committed.
- `/etc/prometheus/file_sd/public-critical-targets.yml` is hand-managed on the VM (the role only references its path); it was edited on 2026-10-10 and 2026-10-12 and has no copy in git. Every `probe_module` it names must exist in `config/blackbox/blackbox.yml` (the repo file the role deploys to /etc/prometheus/blackbox.yml): two modules added only to the live file on 2026-10-10 were wiped by the next deploy (2026-10-11) and the probes for ci.example.org through the edge and badita.example.com DNS-over-HTTPS answered `Unknown module` for a week without any alert; restored 2026-10-19 and `PublicEdgeProbeTargetBroken` (up == 0 for 30 min) now says so. The 2026-10-16 parity check compared rule files and scrape jobs, not module references: check `curl 'http://127.0.0.1:9115/probe?module=<m>&target=<t>'` after editing the target file. `node-targets.yml` and the Scanopy file_sd files are produced by their own timers.
- `/etc/alertmanager/ntfy-password`, the triage token and the secondary ntfy token file are written out of band (controller-local files / one-off minting); the role installs the first two from controller-local sources only.
- The ntfy topic names for the secondary server are read from `{{ repo_shared_local_root }}/ntfy/tier0-topics.yml` on the controller; without that file the secondary webhooks are simply not rendered (the gate then reports the live ones as drift).
