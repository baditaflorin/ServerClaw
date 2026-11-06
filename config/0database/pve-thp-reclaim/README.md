# pve-thp-reclaim: hidden reclaimable memory on a hypervisor with ballooned VMs

Installed on the 0database Proxmox host (`pve01`). The host is not managed by Ansible or fleet-runner, so this directory is the source
of truth: change a file here through a PR, then install it as below. The same files work unchanged on any Proxmox host that balloons
VMs (the 0mcp/lv3 host showed the same effect, about 5 GB, on 2026-10-16); install them there the same way when it matters.

## What it does and why
Guest RAM of a QEMU VM is transparent-huge-page backed (`/sys/kernel/mm/transparent_hugepage/enabled` = `madvise`). Each time the
balloon shrinks a VM, the kernel splits 2 MB pages partly and queues the huge page on the deferred-split list. The unmapped tails stay
allocated until a shrinker runs under memory pressure. They are reclaimable, but `MemAvailable` does not count them, so the host looked
like it had 4-8% available memory for hours while 8-13 GB could be taken back (pve01, 2026-10-16 and again 2026-10-17: a false
`ProxmoxHostMemoryExhausted`, and the CI builder VM trimmed by mistake). One `echo 2 > /proc/sys/vm/drop_caches` runs the shrinkers once
(slab and deferred split) in seconds and touches no guest: 8.7 s, 8,169 MB freed, no load change.

`pve-thp-reclaim` runs every minute (timer). The gap is `(nr_active_anon - nr_anon_pages) * 4 KiB` from `/proc/vmstat`. At or above the
threshold (default 1024 MB) it drops the slab caches and reads the gap again. An action that frees less than 256 MB means the gap is not
deferred-split memory, so it backs off for 15 minutes instead of acting every minute. At pve01's rate (about 45 MB a minute while a
balloon is shrinking, nothing otherwise) the gap never gets past roughly 1.1 GB.

| File here | Live path | Owner, mode |
|---|---|---|
| `pve-thp-reclaim` | `/usr/local/sbin/pve-thp-reclaim` | root:root 0755 |
| `pve-thp-reclaim.service`, `pve-thp-reclaim.timer` | `/etc/systemd/system/` | root:root 0644 |

Optional `/etc/default/pve-thp-reclaim` (read by the service, not in git): `PVE_THP_RECLAIM_THRESHOLD_MB`,
`PVE_THP_RECLAIM_MIN_GAIN_MB`, `PVE_THP_RECLAIM_BACKOFF_SECONDS`.

## Metrics
The run writes `/var/lib/prometheus/node-exporter/textfile/pve_thp_reclaim.prom` (atomically; the node exporter's textfile directory):
`pve_thp_deferred_split_bytes` (after the run), `pve_thp_deferred_split_before_bytes`, `pve_thp_reclaim_threshold_bytes`,
`pve_thp_reclaim_backoff_active`, `pve_thp_reclaim_runs_total`, `pve_thp_reclaim_actions_total`, `pve_thp_reclaim_ineffective_total`,
`pve_thp_reclaim_reclaimed_bytes_total`, `pve_thp_reclaim_last_action_duration_seconds`, `pve_thp_reclaim_last_action_timestamp_seconds`
and `pve_thp_reclaim_last_run_timestamp_seconds` (the dead-man's value). The script exits 1 when `/proc/vmstat` has no such counters:
the unit shows failed and the textfile stops moving. State (counters, back-off) is in `/var/lib/pve-thp-reclaim/state`.

## Install or update
1. Copy the three files to the host (`scp ... <host>:/tmp/`), back up what is there (`sudo cp -p <live> <live>.bak-$(date -u +%Y%m%d)`).
2. `sudo install -o root -g root -m 0755 /tmp/pve-thp-reclaim /usr/local/sbin/pve-thp-reclaim` and
   `sudo install -o root -g root -m 0644 /tmp/pve-thp-reclaim.service /tmp/pve-thp-reclaim.timer /etc/systemd/system/`.
   `sha256sum` on the host must equal `shasum -a 256` of the file here.
3. `sudo systemctl daemon-reload && sudo systemctl enable --now pve-thp-reclaim.timer`.
4. Test: `sudo systemctl start pve-thp-reclaim.service`, then `journalctl -u pve-thp-reclaim.service -n 3` and
   `grep -v '^#' /var/lib/prometheus/node-exporter/textfile/pve_thp_reclaim.prom` (`pve_thp_reclaim_runs_total` moves every minute).
   To see an action on demand: `sudo PVE_THP_RECLAIM_THRESHOLD_MB=0 PVE_THP_RECLAIM_STATE_DIR=/tmp/thp-test PVE_THP_RECLAIM_PROM=/tmp/thp-test.prom /usr/local/sbin/pve-thp-reclaim`
   (scratch state and metrics paths, the real `drop_caches`).

Rollback: `sudo systemctl disable --now pve-thp-reclaim.timer`, remove the three files and `/var/lib/pve-thp-reclaim`. Nothing else on the
host changes; the kernel runs the same shrinkers itself under real memory pressure.

## Alerts
`go-fleet-metrics-hub` `prometheus/rules/thp-reclaim-alerts.yml`: `PveThpReclaimStale` (no check for 10 minutes) and
`PveThpGapHigh` (more than 4 GB of deferred-split memory for 15 minutes: the reclaim is not keeping up or does not apply).
`ProxmoxHostMemoryExhausted` / `ProxmoxHostMemoryHeadroomLow` descriptions tell a responder to look at this gap first.

## Tests
`tests/test_pve_thp_reclaim.py` runs the script against fake `/proc/vmstat` files and a stub reclaim command: below and above the
threshold, the counters, the back-off after an action that frees little, the threshold override, an unreadable vmstat and the lock.
