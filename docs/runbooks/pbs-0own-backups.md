# own-pbs: 0own guest backups, verification, notifications, freshness alerts and the restore drill

Written 2026-10-13 after the 0database + 0own re-audit. own-pbs is VM 620 on the 0own hypervisor (`ssh 0own_pbs`,
PBS 4.2.8, datastore `own-pbs` on `/mnt/pbs-datastore/store`, 4.0 TiB). PBS and its datastore run on **UTC**; the 0own
hypervisor runs on **EEST** (UTC+3) and the other hypervisors on CEST (UTC+2). A time below is written in the clock of the host
that owns it.

## What exists now

| Piece | Where | Detail |
| --- | --- | --- |
| Verify jobs | own-pbs | Five per-namespace slices (six from 2026-10-19 until 2026-10-22, when namespace `0mcp-legacy` and its slice were deleted), each `max-depth 0`, `ignore-verified 1`, `outdated-after 30`: `verify-own-pbs-0database` tue 07:00, `-0infer` tue 10:00, `-0own` wed 07:00, `-0docker` fri 07:00, `-root` sat 07:00 (UTC). They replace the single `verify-own-pbs-weekly` (sun 06:30), which could not finish before Monday's backups: see "Verification schedule" below. |
| Notifications | own-pbs | Webhook endpoint `pbs-ntfy-critical` (POST to `https://ntfy.example.org/platform-proxmox-critical`, user `pbs-notify`, publish-only) and matcher `pbs-ntfy-errors` (severity `error` and `warning`, every task type: gc, verify, prune, sync). The built-in `default-matcher` (mail to root) is untouched. Password: vault `pbs-notify-ntfy-password`. The secret lives only in the PBS notification secret store. |
| 0own namespace | own-pbs | namespace `0own`, user `backup-0own@pbs`, token `vzdump-0own`, ACLs `DatastoreBackup` + `DatastoreAudit` on `/datastore/own-pbs/0own` for both. Token secret: vault `pbs-0own-vzdump-token-secret`, and `/etc/pve/priv/storage/own-pbs-0own.pw` (0600) on the 0own hypervisor. |
| PVE storage | 0own hypervisor | `own-pbs-0own` (server 10.60.10.20, datastore `own-pbs`, namespace `0own`, `prune-backups keep-all=1`: retention belongs to the PBS prune job). |
| Backup jobs | 0own hypervisor | `own-guests-nightly-pbs` VMs 630, 640, 650, 660, 670 at `04:00` EEST (= 03:00 CEST), `own-build-worker-nightly-pbs` VM 610 **weekly since 2026-10-19**, `sun 11:00` EEST (= 08:00Z; it was nightly: the build worker's churn of 0.4-1.2 TiB a day was too much for the shared HDD mirror; its alerts are the weekly pair below). Snapshot mode, `bwlimit 51200` (50 MiB/s), `ionice 7`. PVE job ids cannot start with a digit. The old local job `github-mirror-nightly` (VM 640 to `local`, 03:15, keep-last 7) is unchanged, so VM 640 now has a local copy and a PBS copy. |
| Prune job | own-pbs | `prune-0own`, `04:45` UTC, keep-last 3 + keep-weekly 1 for namespace `0own` (`max-depth 0`). |
| Excluded | | VM 620 itself (own-pbs: it would back up into itself and its 4 TiB disk is the datastore). Nothing else is excluded. |
| Freshness metrics | own-pbs | `/usr/local/sbin/pbs-backup-metrics` (source `scripts/pbs_backup_metrics.py`) run by `pbs-backup-metrics.timer` every 5 min, writes `/var/lib/prometheus/node-exporter/textfile/pbs_backup.prom`: newest snapshot time and snapshot count per namespace/type/id. Walks the datastore tree, needs no token. |
| Alerts | 0mcp Prometheus | `config/prometheus/rules/fleet-backup-freshness.yml` (live copy `/etc/prometheus/rules/fleet-backup-freshness.yml`, reload with `systemctl kill --kill-whom=main --signal=HUP 0mcp-prometheus.service`). |

## Alerts

* The `PgBackup*` alerts (stale, stale critical, last run failed, size shrank, duration high) were removed on 2026-10-21 with the
  job they watched: `pg-primary-daily-pbs` (VM 100, the DomainScope hot standby on the 0database hypervisor) was disabled when the VM
  was shut down for the pve01 retirement (12:07Z), and nothing else writes `pg_backup_*`. They are in git history (the commit before this
  change) if another Postgres VM gets a vzdump job with `vzdump-pg-metrics-hook`. The whole PBS namespace `0database` (host/pve01 and
  vm/100 to vm/103, last snapshots 2026-10-21 00:30Z to 03:22Z) stays in PBS and is excluded from the two daily alerts below, because the
  0database fleet is being sunset; prune the groups when the data is no longer wanted and drop the exclusion.
* `DockerhostStateBackupFailed` (warning, 30 min): `dockerhost_state_backup_last_status == 0`, written by the file-level backup of the Docker host
  (`config/0docker/dockerhost-state-backup`, group `0docker/host/dockerhost-state`, nightly 17:30Z): the run failed, was skipped because the host was busy, or
  finished with warnings. `journalctl -u dockerhost-state-backup -n 80` on VM 100.
* `PbsBackupGroupStale` (> 26 h) and `PbsBackupGroupStaleCritical` (> 50 h) for every PBS backup group of every fleet,
  including the 0own guests. Excluded by design: the namespace `0database` (being sunset), root vm/130 (the CI build VM: no nightly backup since 2026-10-22, its newest 2 snapshots stay; `0mcp-legacy` was deleted the same day), the paused VM-level group `0docker/vm/100` (the Docker host is backed up file by file instead, see above) and the retired root-namespace groups
  vm/101, vm/104, ct/107, ct/108, ct/109 (the 0docker guests were backed up in the root namespace before they moved to namespace
  `0docker` on 2026-10-10). VM 153 runs at 12:00 daily and fits inside 26 h. If a guest is retired on purpose, prune its group in
  PBS and extend the exclusion.
* `PbsBackupGroupWeeklyStale` (> 8 days, warning) and `PbsBackupGroupWeeklyStaleCritical` (> 15 days) for the one group whose job is
  weekly: `0own/vm/610`, the build worker. The daily pair skips that group (the same selector sits in an `unless` line of both
  rules), because the age of a weekly group peaks at 7 days just before the Sunday run and would otherwise page "no backup for 50
  hours" on every Tuesday. 8 days = one missed Sunday plus a day of slack; 15 days = two missed Sundays. **When a job's schedule
  changes, change its alerts in the same PR**: back to nightly = delete the two `unless` lines and this pair; another weekly group =
  add its selector to all four rules (`tests/test_fleet_backup_freshness.py` checks that they name the same group). Found 2026-10-20:
  the job went weekly on 2026-10-19 and the alert still expected a daily run, so a critical page was due on 2026-10-21 for a healthy backup.
* `PbsBackupMetricsStale` / `PbsBackupMetricsMissing`: the collector itself stopped.
* `PbsDatastoreDiskSaturated` (warning): the datastore disk's busy time, 4 h average, above 90 % for 30 min (host `own-pbs`, the OS disk `sda` excluded). Normal nights peak at 45-80 % (2 h average); a GC alone is 99 % for
  about 1.85 h and stays under the 4 h average; a verify run or a stuck sync does not. It exists because the 2026-10-19 stall was first noticed as stale backups a day later. First look: `proxmox-backup-manager task list` for a running verify/GC/sync,
  stop that, not the backups.
* Not duplicated: `PveBackupFreshnessLow` / `PveBackupFailureRecent` (0docker host exporter) and `PBSDatastore*` (capacity).
  The PVE exporter has no per-job backup series on any host, so the PBS-side collector is the single source for the rest.

Proof of the Postgres hook (historic, its alerts are gone, see above): `/usr/local/sbin/vzdump-pg-metrics-hook` on pve01 parses `/var/log/vzdump/qemu-100.log`. A dry run on a
copy of the hook (state and output redirected to a temp dir) against the log of the 2026-10-13 02:30 CEST run produced
`pg_backup_size_bytes 128945655644` (120.09 GiB) and `pg_backup_duration_seconds 1281` where the live file still shows the hand-set
644245094400 and 6345. The live metrics are proven by the 2026-10-14 02:30 CEST run.

## Capacity

Real (thin, compressed ZFS) usage of the 0own guest disks on 2026-10-13: VM 610 179 GiB (2 TiB virtual disk), 630 59.5 GiB,
640 19.7 GiB, 650 1.7 GiB (500 GiB virtual), 660 6.0 GiB, 670 1.3 GiB, in total about 267 GiB. PBS compresses with zstd and
deduplicates, so the expected first-backup footprint is 150-270 GiB, worst case about 370 GiB (ZFS compress ratio 1.4x undone).
The datastore was 66% used (2.6 of 4.0 TiB): after the seed it lands at 71-74%, under the 80% limit, so every guest is included.
Daily growth is the dirty data of 610 (CI worker, the busiest) plus a few GiB for the others, bounded by keep-last 3 + weekly 1.
The datastore is the 5 TiB zvol `rpool/data/vm-620-disk-1` (4 TiB until 2026-10-22, see "Capacity on 2026-10-22") on the same mirror of two HDDs that holds the guests: pool 7.27 TiB,
2.99 TiB allocated.

**The 0own backups are not off-site and not off-pool.** PBS lives on the same ZFS pool as the guests, so this protects against
guest corruption, bad changes and accidental deletion, not against loss of the 0own hypervisor or its disks. An off-host copy is a
separate decision (sync job to another PBS or a Storage Box).

`bwlimit` limits logical bytes read **including zeroes**: a 32 GiB guest with 1.3 GiB used took 658 s at 49.8 MiB/s. The seed of the
big thin disks is therefore slow by design: 610 (2 TiB) about 11-12 h, 650 (500 GiB) about 3 h, 660 about 1 h, 640 45 min. This is
why VM 610 has its own job (it cannot delay the small guests) and why the nightly runs after the seed are short (dirty bitmap).
The first runs overlap the working day on 2026-10-14; the alerts only fire after 26 h.

## Capacity on 2026-10-22: 92 % full, what was found and what was done

**Found (read-only, 2026-10-22 07:00Z).** The datastore (4,328 GB) was 92 % full with 348 GB free and lost 130-260 GB a night net: free space right after the 22:00Z GC was 1,384 GB (10-17), 1,020, 927, 710 and 643 GB (10-21); the projection was
full around 10-25, when every fleet's nightly backup would have failed. Live referenced data was 3,638 GB (84 %) before any garbage. Uploads per night (server task logs, `Upload size`) were 930-1,200 GB in total: the prod Postgres VM 701 (150-450 GB),
the CI build VM 130 (217-239 GB; it rewrites about 326 GiB of its 420 GiB disk every night and held 12 snapshots of about 40 GB each), VM 120 (30-250), VM 702 (70), 0docker VM 101 (40-120), `host/dockerhost-state` (97 the first night, 19 after), CT 108 and `host/ct108-live` (about 50).

**The GC lag (the thing to remember).** A chunk that a snapshot references is touched by the GC's mark phase (atime = that GC's time); the sweep only removes chunks older than the cutoff (24 h 5 min). So data pruned or deleted on day N has
its chunks touched at the GC of day N (before the prune, if the prune runs at 04:00 and the GC at 22:00) and is removed at the GC of day N+2: **space returns 40-48 hours after a prune or a delete**, and the "Pending removals" line of the GC log (239.7 GiB on 10-21) is
exactly what the next GC removes (179,659 pending chunks on 10-20, 179,644 removed on 10-21). A capacity decision therefore has to be made two days ahead. `gc-atime-cutoff` (datastore tuning, minutes) would shorten the lag; it was not changed (the oldest-writer guard
should make a short cutoff safe, but this is the only copy of several fleets' history).

**Why it keeps growing.** The retention windows are still filling: root and 0docker keep daily 7 + weekly 4 + monthly 6 + last 3 (up to 17 snapshots per group, 12 now) and every retained snapshot of a high-churn VM pins its own unique chunks.
PBS prune jobs select by namespace only (no group filter): a per-group retention needs the datastore's prune API per group (`proxmox-backup-debug api create /admin/datastore/own-pbs/prune --backup-type vm --backup-id <id> --keep-last N [--ns X] [--dry-run true]`) or a tool like
`config/0infer/tier0-pbs2/pbs-group-retention` (PBS #2).

**Measure before deleting.** `config/0infer/tier0-pbs2/pbs-prune-whatif.py` is read-only and works on any datastore: `ssh 0own_pbs 'sudo -n env PBS_STORE=/mnt/pbs-datastore/store nice -n 19 ionice -c3 python3 - drop=ns/X/vm/1,... keep-last=3:vm/130' < pbs-prune-whatif.py`
prints the exact bytes a scenario frees (chunks that only the deleted snapshots hold). It reads every index file: **622 s** on this saturated disk at idle I/O priority with the verify slice running, about 1 GB of memory. Group names must exist (it refuses unknown ones before computing anything).

**Done on 2026-10-22 (the user said yes to each; configs backed up under `/root/pbs-config-backups/` on own-pbs and as `/root/*.pre-*` on the hypervisors).**
1. Namespace `0mcp-legacy` deleted (25 groups, 49 snapshots from 2026-09-28..10-05, obsolete copies from before the namespace split; no protected snapshot; the listing is in `approved-deletions-listing-20261022T075948Z.txt`), with its verify job and its prune job. The running legacy verify was stopped first (one ntfy notice).
2. CI build VM 130: excluded from the 0mcp nightly job (`pvesh set /cluster/backup/fleet-nightly-0mcp --exclude 130`, job file backed up as `/root/jobs.cfg.pre-exclude-vm130-20261022T080057Z` on 0mcp) and its group on own-pbs pruned to the newest 2 snapshots (10 deleted, dry run first). The two daily stale alerts skip root vm/130. Bring it back by deleting the exclusion and the alert skip.
3. The Proxmox snapshot `scanopy-access-recovery-20261009` of VM 620 (a rollback point from before a Scanopy install, 13 days old) pinned 1.11 TB of the 0own pool without helping the datastore: deleted (`qm delsnapshot`, freed in minutes; pool 74 % -> 69 %). Then the datastore disk was grown online from 4 to 5 TiB: `qm resize 620 scsi1 +1T` on 0own, in the guest `growpart /dev/sdb 1` and `resize2fs /dev/sdb1` (ext4, mounted, no downtime), `sgdisk -e /dev/sdb` to move the backup GPT; partition table backups `sdb-gpt.pre-grow-20261022T080440Z.bin` and `sdb.sfdisk.pre-grow-20261022T080440Z.txt` in `/root/pbs-config-backups/` on own-pbs. Result: 5,410 GB, 1,430 GB free (74 %), immediately. The growth cannot be undone.
4. On PBS #2 the 0database copies were already gone (250.6 GB by the what-if) when this was run; its `pull-0database` job lost its schedule (comment says so; re-enable with `proxmox-backup-manager sync-job update pull-0database --schedule 17:00`) so the retired pve01 snapshots of PBS #1 are not copied back.

**Expected (exact, from the what-if run of 2026-10-22, 1,113 s):** the 22:00Z GC of 10-22 returns about 240 GiB (pending chunks); the 10-23 GC returns the namespace deletion (281.7 GB: vm/120 80.3, vm/130 82.6, vm/153 47.8, vm/101 22.8, ct/108 13.2, the rest small) and the VM 130 prune (485.2 GB), together about 767 GB, ready around 23:30Z on 10-23; VM 130's nightly 220 GB upload and about 5 hours of write time are gone. Not done, measured for a later decision: the frozen `0docker/vm/100` VM-level group cut to its newest 2 (7 of 9 snapshots, 246.9 GB), the 28 GB of `0database` snapshots that are still on own-pbs (vm/101 23.0 GB, vm/102 4.8 GB). The retained set still grows while the windows fill: watch the post-GC free space of the next two weeks (`node_filesystem_avail_bytes{instance="100.64.0.11:9100",mountpoint="/mnt/pbs-datastore"}` at 23:xx) and decide on per-group retention for the next high-churn VM before the next 85 %.

## Restore drill (lite), 2026-10-13

Evidence and timings: `outputs/restore-drill-2026-10-13.md` in the operator workspace; summary here.

### A. Read-only map of the latest Postgres backup (no Postgres started)

On pve01 (0database hypervisor), using the storage's own token (the writer owns its snapshots and can read them; no extra token was
needed):

```sh
FP=$(grep -A9 'pbs: own-pbs-0database' /etc/pve/storage.cfg | awk '/fingerprint/{print $2}')
export PBS_REPOSITORY='backup-0database@pbs!vzdump-0database@100.64.0.11:own-pbs' PBS_FINGERPRINT="$FP"
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
  (`/etc/nftables.conf`) opens tcp 9100 on `tailscale0` for `100.64.0.4` only. Both are scraped by 0mcp Prometheus through Scanopy
  discovery (job `node_exporter`). 670 was configured through `qm guest exec` because our SSH key is not accepted there.
* **qemu-guest-agent**: VM 650 had no package (installed and enabled); VM 640 had it running but the host reported "not running" (stale
  channel), fixed with `systemctl restart qemu-guest-agent` in the guest. Both answer `qm agent <id> ping`, so fs-freeze now works for
  the backups. No reboot was needed.

## Verification schedule (2026-10-19)

**What happened.** The single weekly job `verify-own-pbs-weekly` (sun 06:30 UTC) had been running for 22.5 h when it was stopped at 05:09 UTC on Monday 2026-10-19 (`task stop`, "verification failed - job aborted", one ntfy
notice): group 39 of 77, its log silent for 5 h on one 508 GB image (`vm/130` in the root namespace). The datastore disk `sdb` (a virtual disk on the 0own hypervisor's spinning ZFS mirror) was 92-98 % busy since Sunday
06:00 while delivering only 6-28 MiB/s of random reads (about 27 IOPS), and the nightly backups of every fleet crawled behind it: 0database's pg-primary took 4 h 33 min (41-46 min normally) and held that
hypervisor's global vzdump lock, so its 03:15 job for VMs 101-103 died with `can't acquire lock '/var/run/vzdump.lock' - got timeout` after 180 min (re-run by hand); 0mcp's nightly job grew from 27 min (10-11) to 280 min (10-18)
and 310+ min; 0own's jobs ran 2-4 h long; VM 100 on 0docker spiralled twice (see fleet-state `hypervisor-0docker/README.md`). This runbook's own first note on the job ("it can reach Monday 00:00 UTC, when the 0mcp backups start") foresaw it; the assumed 50 MiB/s was in fact 25.

**Why a weekly pass cannot fit.** A verify run reads every chunk of every snapshot it verifies, once per run (the in-run cache does not survive the run). "Later runs only verify new snapshots" holds, but a new snapshot of a
group still costs a read of that group's whole chunk set. One pass over the referenced data (3.18 TB on 2026-10-19; per namespace, exclusive GB: root 1,063, 0docker 559, 0own 292, 0mcp-legacy 280, 0infer 226, 0database 181)
is about 35 h at the 25 MiB/s this disk gives, longer than the gap between two backup windows.

**What is configured now.** One job per namespace on its own weekday, in the daytime, so none overlaps the nightly window (00:00-06:00 UTC) or another slice. The GC, which saturates the disk (99 % busy at only about 1.5 MiB/s of metadata I/O, 1.85 h per run) and starved the backups that overlapped it, moved from `5,17:30` (twice a day, inside the backup window and the verify hours) to **once a day at 22:00 UTC** (`proxmox-backup-manager datastore update own-pbs --gc-schedule 22:00`, backup `/root/pbs-config-backups/datastore.cfg.pre-gc-move-20261019T053151Z`; it ends about 23:50, before the 00:00 backups). Daily timeline (UTC): 00:00-06:00 backups, 06:00-07:00 free, 07:00-20:00 one verify slice (tue-sat), 22:00-23:50 GC. Slices:
root sat 07:00 (about 13 h at 25 MiB/s, the long one), 0docker fri 07:00 (about 7 h), 0own wed 07:00 (about 3.5 h), 0mcp-legacy thu 07:00 (about 3.5 h), 0infer tue 10:00 (about 2.5 h), 0database tue 07:00 (about 2 h). The total work
is unchanged, the longest slice ends about 20:00. Config backup: `/root/pbs-config-backups/verification.cfg.pre-ns-split-20261019T051653Z`.

**Check after the first runs (tue 10-20 to sat 10-24):** `proxmox-backup-manager task list --all --limit 40 | grep verif` for start/end times. If the root slice ends after 23:00 (slower disk, bigger namespace), move it earlier or
decide on a monthly cadence; if the disk is replaced by SSD this section is moot. Namespaces without a job are not verified: a new namespace needs its own `verify-job create <id> --store own-pbs --ns <ns> --max-depth 0 ...`
(`max-depth 0` means children are NOT covered).

**Gotchas.** PBS limits a job comment to 128 characters. `proxmox-backup-manager task list` and `task log` of a huge running job are slow on this saturated host: read the log file directly
(`tail /var/log/proxmox-backup/tasks/<xx>/<UPID>`, UPIDs contain a literal `\x2d`, so quote them and do not pass them through `xargs`).

## A snapshot backup of a live database needs fleecing or a fast target (2026-10-19)

**What happened.** The 0infer job `infer-guests-nightly-pbs` (03:00 node time = 01:00 UTC) was created on 2026-10-14 when VM 701 was still an empty database VM. At the 2026-10-18 cutover VM 701 (`infer-pg-primary`) became the production
DomainScope Postgres primary and the job was not revisited. On 2026-10-19 its snapshot backup onto this PBS (about 18 MiB/s at that hour, every fleet writing) throttled the guest's writes through QEMU's copy-before-write: from 01:15 to 02:45 UTC its
I/O wait pressure sat at 71-90 %, disk writes fell to about 0 MiB/s (normally 5-7), a checkpoint took 5,258 s instead of about 810 s (longest fsync 172 s), 1,616 statements ran 10 s or more and DomainScope categorize was effectively down for 80 minutes. Load never passed 7 and blocked
tasks never passed 4, so no load-based signal saw it; the I/O wait pressure (`node_pressure_io_waiting_seconds_total`) shows it plainly.

**The rule.** A snapshot-mode vzdump makes every first write to a not-yet-backed-up 4 MiB chunk wait until the old chunk has reached the backup target. With a slow target (this PBS: 9-57 MiB/s depending on the hour) that wait is the guest's write latency. Either the target must be faster than the guest's
write burst, or the backup must use fleecing (`--fleecing enabled=1,storage=<fast local storage>`: the old chunk goes to a local image first and the guest never waits for the PBS). Fleecing needs room on the storage and a PVE with it (8.2+); the 0docker hypervisor has none (root filesystem 60-99 GiB free,
the host's recovery timer trims guests below 60 GiB), pve01 has 48 GB on `local` and a thin pool at 80 %, 0own is two spinning disks; 0infer has 581 GB on a separate SSD.

**What is configured on 0infer now** (config backups `/root/jobs.cfg.pre-fleecing-split-20261019T162021Z`, `/root/jobs.cfg.pre-pg-reschedule-20261019T162915Z` and `/root/jobs.cfg.pre-guests-reschedule-20261019T163012Z` on the hypervisor): `infer-pg-nightly-pbs` = VM 701 alone, 06:30 node time (**04:30 UTC**: after the 0docker VM job at 04:00 UTC, which backs up the production DomainScope VM 101 without fleecing and must not share the PBS with a 126 GiB upload, and before the daytime verify slices; it first went in at 03:00 UTC and was moved the same afternoon when that overlap showed up), fleecing on `local`, `bwlimit 102400`; `infer-guests-nightly-pbs` = VM 702 and 703 at **03:00 UTC** (05:00 node time) with the same fleecing and cap (before the split they effectively started at about 03:00 UTC behind VM 701's two hours; 01:00 UTC is the busiest PBS hour and the slot of CT 108's stop-mode backup, whose outage grows with every competing upload);
`infer-tier0-nightly-pbs` = VM 704 at 00:30 UTC unchanged. Tested on VM 702 first (58 GiB in 13 minutes, the fleece image `vm-702-fleece-0.qcow2` created on `local`, 21 MiB at most, removed at the end). A 2.3 TB metadata-preallocated fleece image formats in 78 s and uses 365 MiB, so VM 701's two images add
about 80 s before the freeze. The alert `PostgresIoStall` (critical: I/O wait above 60 % for 10 minutes on a host that runs a Postgres cluster) watches for the signature; the daily health report's check I reports the first fleeced run (2026-10-20 03:00 UTC) and the database's I/O wait.

**Watch:** fleece images land on the 0infer root SSD (`sdb`, about 28 % of its life left, a single disk with no RAID). A normal image is a few MiB to GB; if the database's first nights show tens of GB, either accept the wear or find another home for it. The guest freeze at backup start (32 s of no writes on 2026-10-19) is separate: the agent option
`freeze-fs-on-backup=0` removes it and Postgres recovers from a crash-consistent snapshot; that is the database owner's call. A guard like fleet-state's `vzdump-guard` would need the I/O wait pressure as its signal on this VM (its load and blocked-task thresholds would not have fired).

## 0mcp nightly job `fleet-nightly-0mcp`: fleecing on (2026-10-30)

**What happened.** The nightly job (02:00 node time, 01:00 UTC) backs up VM 155, the agent-history store (Postgres), in snapshot mode with `lock: backup`. On 2026-10-30 between 01:14 and 01:22 UTC the guest's writes waited on copy-before-write to the PBS (10-47 MiB/s at that hour): Postgres blocked in `WALWrite`, `/healthz` answered 503 "Database unreachable" and ingest timed out for about 11 minutes (guest I/O wait pressure about 98 %). The collectors queue their events and caught up afterwards, so nothing was lost, but it is the same rule as on 0infer (previous section): a slow target is the guest's write latency unless the backup uses fleecing.

**What is set now.** On the 0mcp hypervisor, by hand with `pvesh` on 2026-10-30 about 07:50 UTC:

```bash
cp -a /etc/pve/jobs.cfg /root/jobs.cfg.pre-fleecing-20261030T0750Z
pvesh set /cluster/backup/fleet-nightly-0mcp --fleecing enabled=1,storage=local-nvme
```

`local-nvme` is the separate `nvme0n1`, mounted at `/var/lib/vz-nvme1` (about 1.2 TB free), not the root filesystem (`md2`). The 0docker case in the previous section (no room for fleece images: a root filesystem with 60-99 GiB free on a host that trims guests below 60 GiB) therefore does not apply here; the 0mcp job writes its fleece images to a disk separate from the root filesystem.

**Tested before it was set**, with one manual `vzdump 155 --mode snapshot --fleecing enabled=1,storage=local-nvme` on VM 155: guest I/O pressure stayed under 2 % (0 to 1.6 %, against about 98 % in the un-fleeced nightly run), `/healthz` answered 200 throughout, ingest had 0 failures (the un-fleeced run stalled for 11 minutes), and the fleece images were removed at the end of the run. The first nightly run with fleecing on the schedule has not been observed yet; check the guest's I/O pressure and `/healthz` around 01:00 UTC after the next run.

**Rollback.** `pvesh set /cluster/backup/fleet-nightly-0mcp --delete fleecing`, or put back `/root/jobs.cfg.pre-fleecing-20261030T0750Z` (the file as it was before, including `exclude 130`; copy it over `/etc/pve/jobs.cfg` only if nothing else changed in the job file since).

**Not in git.** This job is hand-set through `pvesh` and is not declared in any role or inventory file, like its `exclude 130` (2026-10-22). Recreating the job from the repo would silently drop fleecing, and VM 155's nightly backup would stall the store again. If the job is ever put under a role, the role must carry `fleecing: enabled=1,storage=local-nvme`.

**Watch.** The fleece images live on `local-nvme` only while a backup runs (the manual test removed them at its end). If a nightly run ever hangs or fails, look at `df -h /var/lib/vz-nvme1` first.

## Rollback

* Verify jobs: `proxmox-backup-manager verify-job remove verify-own-pbs-<ns>` for the six slices, or put back the pre-split file `/root/pbs-config-backups/verification.cfg.pre-ns-split-20261019T051653Z` on own-pbs (it holds the old `verify-own-pbs-weekly`, sun 06:30); to remove verification altogether remove all of them.
* Notifications: `proxmox-backup-manager notification matcher remove pbs-ntfy-errors; proxmox-backup-manager notification endpoint webhook remove pbs-ntfy-critical`; `ntfy user del pbs-notify` on the ntfy container; delete vault secret `pbs-notify-ntfy-password`.
* 0mcp nightly job fleecing: `pvesh set /cluster/backup/fleet-nightly-0mcp --delete fleecing` on the 0mcp hypervisor (the job file as it was before is `/root/jobs.cfg.pre-fleecing-20261030T0750Z`).
* 0own backups: on the hypervisor `pvesh delete /cluster/backup/own-guests-nightly-pbs` and `.../own-build-worker-nightly-pbs`, `pvesm remove own-pbs-0own`, delete `/etc/pve/priv/storage/own-pbs-0own.pw` (backups of `/etc/pve/jobs.cfg` and `storage.cfg` from before the change are in `/root`); on own-pbs `proxmox-backup-manager prune-job remove prune-0own`, `user delete backup-0own@pbs`; the namespace and its snapshots are removed from the PBS UI or API only when the data is no longer wanted.
* Freshness collector: `systemctl disable --now pbs-backup-metrics.timer` on own-pbs, delete the rules file on monitoring-lv3 and SIGHUP Prometheus (a copy of the pre-change rule set is not needed: the file is new).
* OpenObserve compose: `compose.yaml.bak-pre-logrotate-*` and `edge-compose.yaml.bak-pre-logrotate-*` in `/opt/openobserve`.
* Tailscale policy: rollback copy `/var/lib/tailscale-policy-sync/rollback/policy.20261013T144031Z.*.hujson` on CT108 (`plan --file ... && apply --file ...`); advertise-routes: `tailscale set --advertise-routes=10.60.10.50/32` on the 0own hypervisor (prefs copy `/root/tailscale-prefs.pre-adv-660.json`).
* PBS 4.2.8: a pre-upgrade copy of `/etc/proxmox-backup` is `/root/etc-proxmox-backup-pre-4.2.8-*.tgz` on own-pbs.

## Weekly datastore usage report (added 2026-10-15)
`pbs-usage-report.timer` on the PBS VM (Mon 03:10 UTC, idle I/O priority, ~1.5 to 20 minutes) reads every snapshot index and walks `.chunks`: exclusive bytes per namespace and top groups, on-disk vs referenced bytes, and **unreferenced chunks by atime age**
(`/var/lib/pbs-usage/last-report.txt`; metrics `pbs_usage_*` via the textfile collector). Garbage normally disappears about two GC cycles after a prune; `PBSUnreferencedChunksLingering` fires when more than 300 GB is unreferenced in two consecutive weekly reports,
`PBSUsageReportStale` when no report ran for 10 days (`config/prometheus/rules/pbs-usage.yml`). It never modifies the datastore. First run 2026-10-15: 2587 GB referenced, 3550 GB on disk, 958 GB unreferenced (a prune of the `0mcp-legacy` namespace the same day).

## CT 108 (the builder): weekly image, daily file backup (2026-10-28)

`ct108-nightly` (vzdump, stop mode: the builder is down for the upload) runs **Sundays 03:30 CEST** since 2026-10-28. The daily restore point is the
file-level `ct108-live-backup` (group `host/ct108-live`, namespace `0docker`, 05:30 CEST, no downtime). Accordingly `PbsBackupGroupStale*` exempt
group `ct/108`, and `PbsBackupGroupStaleWeekly` (8.5 days) / `PbsBackupGroupStaleWeeklyCritical` (16 days) judge it; `host/ct108-live` is a normal daily group.
Details and restore recipe: fleet-state `hypervisor-0docker/README.md`.
