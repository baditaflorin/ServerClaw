# own-pbs: 0own guest backups, verification, notifications, freshness alerts and the restore drill

Written 2026-10-13 after the 0database + 0own re-audit. own-pbs is VM 620 on the 0own hypervisor (`ssh 0own_pbs`,
PBS 4.2.8, datastore `own-pbs` on `/mnt/pbs-datastore/store`, 4.0 TiB). PBS and its datastore run on **UTC**; the 0own
hypervisor runs on **EEST** (UTC+3) and the other hypervisors on CEST (UTC+2). A time below is written in the clock of the host
that owns it.

## What exists now

| Piece | Where | Detail |
| --- | --- | --- |
| Weekly verify job | own-pbs | `verify-own-pbs-weekly`, `sun 06:30` (after the 05:30 GC), `ignore-verified 1`, `outdated-after 30`. The first run verifies every snapshot of every namespace (about 2.6 TiB, expect many hours; at the 50 MiB/s the earlier 411 GB verify ran at it can reach Monday 00:00 UTC, when the 0mcp backups start). Later runs only verify new snapshots. |
| Notifications | own-pbs | Webhook endpoint `pbs-ntfy-critical` (POST to `https://ntfy.example.org/platform-proxmox-critical`, user `pbs-notify`, publish-only) and matcher `pbs-ntfy-errors` (severity `error` and `warning`, every task type: gc, verify, prune, sync). The built-in `default-matcher` (mail to root) is untouched. Password: vault `pbs-notify-ntfy-password`. The secret lives only in the PBS notification secret store. |
| 0own namespace | own-pbs | namespace `0own`, user `backup-0own@pbs`, token `vzdump-0own`, ACLs `DatastoreBackup` + `DatastoreAudit` on `/datastore/own-pbs/0own` for both. Token secret: vault `pbs-0own-vzdump-token-secret`, and `/etc/pve/priv/storage/own-pbs-0own.pw` (0600) on the 0own hypervisor. |
| PVE storage | 0own hypervisor | `own-pbs-0own` (server 10.60.10.20, datastore `own-pbs`, namespace `0own`, `prune-backups keep-all=1`: retention belongs to the PBS prune job). |
| Backup jobs | 0own hypervisor | `own-guests-nightly-pbs` VMs 630, 640, 650, 660, 670 at `04:00` EEST (= 03:00 CEST), `own-build-worker-nightly-pbs` VM 610 at `04:30` EEST. Snapshot mode, `bwlimit 51200` (50 MiB/s), `ionice 7`. PVE job ids cannot start with a digit. The old local job `github-mirror-nightly` (VM 640 to `local`, 03:15, keep-last 7) is unchanged, so VM 640 now has a local copy and a PBS copy. |
| Prune job | own-pbs | `prune-0own`, `04:45` UTC, keep-last 3 + keep-weekly 1 for namespace `0own` (`max-depth 0`). |
| Excluded | | VM 620 itself (own-pbs: it would back up into itself and its 4 TiB disk is the datastore). Nothing else is excluded. |
| Freshness metrics | own-pbs | `/usr/local/sbin/pbs-backup-metrics` (source `scripts/pbs_backup_metrics.py`) run by `pbs-backup-metrics.timer` every 5 min, writes `/var/lib/prometheus/node-exporter/textfile/pbs_backup.prom`: newest snapshot time and snapshot count per namespace/type/id. Walks the datastore tree, needs no token. |
| Alerts | 0mcp Prometheus | `config/prometheus/rules/fleet-backup-freshness.yml` (live copy `/etc/prometheus/rules/fleet-backup-freshness.yml`, reload with `systemctl kill --kill-whom=main --signal=HUP 0mcp-prometheus.service`). |

## Alerts

* `PgBackupStale` (> 26 h, warning) and `PgBackupStaleCritical` (> 50 h) on `pg_backup_last_success_timestamp_seconds{method="vzdump"}`;
  `PgBackupLastRunFailed` (`pg_backup_last_status != 1`, critical).
* `PgBackupSizeShrank` (below 70% of the 7-day average) and `PgBackupDurationHigh` (above 3x the 7-day median), severity **info**.
  `size_bytes` is the figure vzdump logs as "transferred": a dirty-bitmap run transfers only changed blocks, so it follows write
  volume. Both are gated on `time() > 2026-10-21` because the series still holds a hand-set sample (644245094400 bytes, 6345 s)
  until the fixed hook has run on 2026-10-14 02:30 CEST and that sample has left the 7-day window.
* `PbsBackupGroupStale` (> 26 h) and `PbsBackupGroupStaleCritical` (> 50 h) for every PBS backup group of every fleet,
  including the 0own guests. Excluded by design: namespace `0mcp-legacy` (frozen archive) and the retired root-namespace groups
  vm/101, vm/104, ct/107, ct/108, ct/109 (the 0docker guests were backed up in the root namespace before they moved to namespace
  `0docker` on 2026-10-10). VM 153 runs at 12:00 daily and fits inside 26 h. If a guest is retired on purpose, prune its group in
  PBS and extend the exclusion.
* `PbsBackupMetricsStale` / `PbsBackupMetricsMissing`: the collector itself stopped.
* Not duplicated: `PveBackupFreshnessLow` / `PveBackupFailureRecent` (0docker host exporter) and `PBSDatastore*` (capacity).
  The PVE exporter has no per-job backup series on any host, so the PBS-side collector is the single source for the rest.

Proof of the Postgres hook: `/usr/local/sbin/vzdump-pg-metrics-hook` on pve01 parses `/var/log/vzdump/qemu-100.log`. A dry run on a
copy of the hook (state and output redirected to a temp dir) against the log of the 2026-10-13 02:30 CEST run produced
`pg_backup_size_bytes 128945655644` (120.09 GiB) and `pg_backup_duration_seconds 1281` where the live file still shows the hand-set
644245094400 and 6345. The live metrics are proven by the 2026-10-14 02:30 CEST run.

## Capacity

Real (thin, compressed ZFS) usage of the 0own guest disks on 2026-10-13: VM 610 179 GiB (2 TiB virtual disk), 630 59.5 GiB,
640 19.7 GiB, 650 1.7 GiB (500 GiB virtual), 660 6.0 GiB, 670 1.3 GiB, in total about 267 GiB. PBS compresses with zstd and
deduplicates, so the expected first-backup footprint is 150-270 GiB, worst case about 370 GiB (ZFS compress ratio 1.4x undone).
The datastore was 66% used (2.6 of 4.0 TiB): after the seed it lands at 71-74%, under the 80% limit, so every guest is included.
Daily growth is the dirty data of 610 (CI worker, the busiest) plus a few GiB for the others, bounded by keep-last 3 + weekly 1.
The datastore is the 4 TiB zvol `rpool/data/vm-620-disk-1` on the same mirror of two HDDs that holds the guests: pool 7.27 TiB,
2.99 TiB allocated.

**The 0own backups are not off-site and not off-pool.** PBS lives on the same ZFS pool as the guests, so this protects against
guest corruption, bad changes and accidental deletion, not against loss of the 0own hypervisor or its disks. An off-host copy is a
separate decision (sync job to another PBS or a Storage Box).

`bwlimit` limits logical bytes read **including zeroes**: a 32 GiB guest with 1.3 GiB used took 658 s at 49.8 MiB/s. The seed of the
big thin disks is therefore slow by design: 610 (2 TiB) about 11-12 h, 650 (500 GiB) about 3 h, 660 about 1 h, 640 45 min. This is
why VM 610 has its own job (it cannot delay the small guests) and why the nightly runs after the seed are short (dirty bitmap).
The first runs overlap the working day on 2026-10-14; the alerts only fire after 26 h.

## Restore drill (lite), 2026-10-13

Evidence and timings: `outputs/restore-drill-2026-10-13.md` in the operator workspace; summary here.

### A. Read-only map of the latest Postgres backup (no Postgres started)

On pve01 (0database hypervisor), using the storage's own token (the writer owns its snapshots and can read them; no extra token was
needed):

```sh
FP=$(grep -A9 'pbs: own-pbs-0database' /etc/pve/storage.cfg | awk '/fingerprint/{print $2}')
export PBS_REPOSITORY='backup-0database@pbs!vzdump-0database@203.0.113.11:own-pbs' PBS_FINGERPRINT="$FP"
export PBS_PASSWORD=$(cat /etc/pve/priv/storage/own-pbs-0database.pw)       # never print it
proxmox-backup-client snapshot list vm/100 --ns 0database
proxmox-backup-client map vm/100/<ts> drive-scsi0.img --ns 0database          # prints /dev/loopN (read-only, RO=1)
mkdir /mnt/restore-drill-vm100 && mount -o ro,noload /dev/loopNp1 /mnt/restore-drill-vm100
pg_controldata -D /mnt/restore-drill-vm100/var/lib/postgresql/18/main
umount /mnt/restore-drill-vm100 && proxmox-backup-client unmap /dev/loopN
```

pve01 has no `pg_controldata`; the binary only needs libc, so the one from pg-primary (`/usr/lib/postgresql/18/bin/pg_controldata`)
was copied to `/tmp` for the run and deleted afterwards. Result for `vm/100/2026-10-13T00:30:12Z` (backup started 02:30:12 CEST):

* ext4 data partition mounted read-only with `noload` (no journal replay, nothing written).
* PG_VERSION 18, `pg_control` version 1800, catalog 202506291, data checksums on, `wal_level replica`.
* Database system identifier 7688231907051079074 = the live primary's identifier.
* Cluster state "in production" (a crash-consistent snapshot, as designed), latest checkpoint 02:14:53 CEST at 659/77CBEA58,
  REDO 659/39E57D08 in WAL file `000000010000065900000039`, `pg_control` last modified 02:28:23 CEST: all before the 02:30:12 start.
* `pg_wal` holds 512 segments from `...065900000039` (the REDO file) to `...065B00000038`, so crash recovery has everything it needs
  (8.1 GiB); `base/` has 35 database directories; data directory 469 GiB.
* Unmapped and unmounted cleanly, no loop device left, no process left.

The drill proves the snapshot is readable, structurally complete and consistent with the live cluster. It does not replay WAL; a
full restore plus a Postgres start on an isolated host (about 600 GiB, hours) is still untested. There is no PITR (archive_mode off).

### B. Real restore of a guest, booted isolated

Guest: VM 670 (pdm), the first real backup in namespace `0own` (`vm/670/2026-10-13T14:31:30Z`, 32 GiB, 92% zeroes).

```sh
qmrestore own-pbs-0own:backup/vm/670/2026-10-13T14:31:30Z 9670 --storage local-zfs --unique 1 --bwlimit 102400
qm set 9670 --delete net0 --name restore-drill-scratch --onboot 0    # no network device at all: nothing can collide with 670
qm start 9670        # qemu guest agent answers after about 30 s; wait for `systemctl is-system-running`
qm guest exec 9670 -- bash -c 'hostname; systemctl --failed --no-legend; ip -br a'
qm stop 9670 && qm destroy 9670 --purge --destroy-unreferenced-disks 1
```

Result: restore of 32 GiB in 38 s (855 MB/s, zeroes skipped), the guest booted with the guest agent answering, `proxmox-datacenter-api`,
`proxmox-datacenter-privileged-api`, `tailscaled`, `scanopy-daemon` and `sshd` active, `/etc/proxmox-datacenter-manager` (remotes.cfg,
auth, acme) intact, root filesystem 1.7 GiB used. Only failures: `cloud-init-main` and `cloud-final` (no network). The only interface
was `tailscale0` with a link-local address and no uplink. Scratch VM 9670 and its zvol were destroyed; VM 670 was never touched.
Do not attach a network to a restored guest that carries a tailscale identity (the restored 670 holds the same node key as the live one).
This isolation is stricter than the bridge-based checks in `backup-restore-verification.md`.

## Other changes of the same day

* **OpenObserve (VM 630, `/opt/openobserve`)**: the containers had unbounded `json-file` logs (the `openobserve` log was 14 GB: every
  ingest request is an INFO access-log line). `compose.yaml` and `edge-compose.yaml` now set `logging: json-file, max-size 100m,
  max-file 5` for postgres, openobserve and caddy, and `/etc/docker/daemon.json` sets the same default for future containers (it only
  takes effect at the next dockerd restart). The stack was recreated (`docker compose --env-file <tmpfs file> up -d`, secrets read from
  the running containers' environment into `/dev/shm`, deleted afterwards); recreating removed the 14 GB log. Ingestion resumed within
  a minute, Vector flushed its buffer. The compose files are copies of the live ones, kept in `config/0own/openobserve/` (they hold
  only `${...}` references). Compose variables: `OO_PG_PASSWORD`, `OO_ROOT_PASSWORD`, `ZO_META_POSTGRES_DSN`. With 100 MB x 5 the log
  window is a few hours; set `ZO_LOG_LEVEL=warn` if more history is wanted.
* **node_exporter on VM 660 and VM 670**: 660 binds `10.60.10.60:9100` (reached over the hypervisor's new `10.60.10.60/32` Tailscale
  route: `tailscale set --advertise-routes=10.60.10.50/32,10.60.10.60/32` on the 0own hypervisor, autoApprover and Prometheus grant in
  `config/tailscale/policy.hujson`); 670 binds its tailnet address `100.65.106.57:9100`, and its nftables input chain
  (`/etc/nftables.conf`) opens tcp 9100 on `tailscale0` for `203.0.113.4` only. Both are scraped by 0mcp Prometheus through Scanopy
  discovery (job `node_exporter`). 670 was configured through `qm guest exec` because our SSH key is not accepted there.
* **qemu-guest-agent**: VM 650 had no package (installed and enabled); VM 640 had it running but the host reported "not running" (stale
  channel), fixed with `systemctl restart qemu-guest-agent` in the guest. Both answer `qm agent <id> ping`, so fs-freeze now works for
  the backups. No reboot was needed.

## Rollback

* Verify job: `proxmox-backup-manager verify-job remove verify-own-pbs-weekly`.
* Notifications: `proxmox-backup-manager notification matcher remove pbs-ntfy-errors; proxmox-backup-manager notification endpoint webhook remove pbs-ntfy-critical`; `ntfy user del pbs-notify` on the ntfy container; delete vault secret `pbs-notify-ntfy-password`.
* 0own backups: on the hypervisor `pvesh delete /cluster/backup/own-guests-nightly-pbs` and `.../own-build-worker-nightly-pbs`, `pvesm remove own-pbs-0own`, delete `/etc/pve/priv/storage/own-pbs-0own.pw` (backups of `/etc/pve/jobs.cfg` and `storage.cfg` from before the change are in `/root`); on own-pbs `proxmox-backup-manager prune-job remove prune-0own`, `user delete backup-0own@pbs`; the namespace and its snapshots are removed from the PBS UI or API only when the data is no longer wanted.
* Freshness collector: `systemctl disable --now pbs-backup-metrics.timer` on own-pbs, delete the rules file on monitoring-lv3 and SIGHUP Prometheus (a copy of the pre-change rule set is not needed: the file is new).
* OpenObserve compose: `compose.yaml.bak-pre-logrotate-*` and `edge-compose.yaml.bak-pre-logrotate-*` in `/opt/openobserve`.
* Tailscale policy: rollback copy `/var/lib/tailscale-policy-sync/rollback/policy.20261013T144031Z.*.hujson` on CT108 (`plan --file ... && apply --file ...`); advertise-routes: `tailscale set --advertise-routes=10.60.10.50/32` on the 0own hypervisor (prefs copy `/root/tailscale-prefs.pre-adv-660.json`).
* PBS 4.2.8: a pre-upgrade copy of `/etc/proxmox-backup` is `/root/etc-proxmox-backup-pre-4.2.8-*.tgz` on own-pbs.

## CT 108 (the builder): weekly image, daily file backup (2026-10-28)

`ct108-nightly` (vzdump, stop mode: the builder is down for the upload) runs **Sundays 03:30 CEST** since 2026-10-28. The daily restore point is the
file-level `ct108-live-backup` (group `host/ct108-live`, namespace `0docker`, 05:30 CEST, no downtime). Accordingly `PbsBackupGroupStale*` exempt
group `ct/108`, and `PbsBackupGroupStaleWeekly` (8.5 days) / `PbsBackupGroupStaleWeeklyCritical` (16 days) judge it; `host/ct108-live` is a normal daily group.
Details and restore recipe: fleet-state `hypervisor-0docker/README.md`.
