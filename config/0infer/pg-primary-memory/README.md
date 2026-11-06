# infer-pg-primary (VM701): the 10 GiB `/dev/shm` cap and the VM memory

2026-10-31. VM701 (`infer-pg-primary`, the production DomainScope Postgres 18 on the 0infer hypervisor) lost nine `postgres` processes to the kernel OOM killer at 01:25Z and
crash-recovered for about 25 s. Two changes were made by hand that morning, by two sessions, and were in no repository. This directory records both, and `install-vm.sh` makes the
first one repeatable. Decision, arithmetic and implementation state: `docs/adr/0495-pg-primary-memory-guardrails.md`. The Postgres settings that bound the same memory
(`max_parallel_workers_per_gather`, `max_parallel_workers`, `temp_file_limit`, `work_mem`) are hostconf files, not here: `config/hostconf/hostconf.yaml`,
ids `postgresql-parallel-guardrails.infer-pg-primary` and `postgresql-work-mem-guardrails.infer-pg-primary`.

## What happened

The memory that ran the VM out was shared memory beyond the main segment, not `/tmp` and not a connection burst by itself. Postgres' dynamic shared memory (DSM, `dynamic_shared_memory_type = posix`)
lives on `/dev/shm`, a tmpfs that was at its default of 50 % of RAM (30 GiB). Parallel queries put their hash tables there.

| Measured | Value |
|---|---|
| Main shared-memory segment (`shared_buffers` 24 GiB) | 24.62 GiB, constant from 01:16 to 01:23:45 |
| `shmem` in the kernel's own OOM report at 01:25:18 | 12,878,605 pages = 49.1 GiB |
| Excess over the segment (the DSM) | +18.3 GiB at the 01:24:00 scrape, +24.5 GiB at the kill |
| Largest excess in the six days before | +4.1 GiB (2-minute grid); +8.1 GiB on 2026-10-21 14:53 in the 14-day series |
| What the settings allowed | 6 simultaneous gathers (24 workers / 4 per gather); one parallel hash node may use `work_mem x hash_mem_multiplier x (workers + 1)` = 512 MB x 2 x 5 = 5.0 GiB for the role `domainscope_app`, 2.5 GiB for every other role; 6 x 5.0 = 30 GiB |

Which statement made the 24.5 GiB is not known (killed statements never log, `pg_stat_statements` was reset by the crash). The incident was three to six times anything seen before, so it needed a plan
change or a new mix of concurrent queries, not the everyday load.

## The cap

| Where | What | How it is kept |
|---|---|---|
| VM701 `/dev/shm` | tmpfs `size=10G` (was 50 % of RAM, 30 GiB) | `/etc/fstab` line `tmpfs /dev/shm tmpfs rw,nosuid,nodev,size=10G 0 0`; applied live on 2026-10-31 at 08:02Z with `mount -o remount,size=10G /dev/shm`, backup `/etc/fstab.bak-shm-<UTC time>` made then; `install-vm.sh` repeats it |

Why 10 GiB: above every DSM figure seen in 14 days (+8.1 GiB at most), far below the 24.5 GiB that killed the cluster, so normal queries are not touched and a runaway one is bounded. The query that needs
more than 10 GiB fails alone with `ERROR: could not resize shared memory segment ... No space left on device` and the log prints its `STATEMENT:`, instead of the whole cluster going down (this is Postgres'
documented behaviour, the same error as with Docker's 64 MB `/dev/shm`; a parallel query ran under the cap on 2026-10-31, but a query over the cap has not been tried on this build). Nothing else of Postgres
uses `/dev/shm` (it held 16-20 MiB when idle). The cap is not a design figure: the settings in the two hostconf files keep the designed ceiling at 3.75 GiB (3 gathers x 1.25 GiB, ADR 0495, amendment of 2026-11-02), and the cap is the backstop.

## The VM memory

| Where | What | How it is kept |
|---|---|---|
| Hypervisor 0infer, VM 701 | `memory: 66560` MiB, `balloon: 66560` (equal to memory: no ballooning), `hotplug` includes `memory` | live hotplug at about 08:17Z on 2026-10-31 (from 60,416 MiB: +6 GiB, in the 5 to 8 GiB that was asked for); `qm config 701` shows it, nothing in git sets it |

Guest `MemTotal` went from 58.87 to 64.87 GiB, 520 memory blocks online. Postgres was not restarted (same postmaster start, 2026-10-30 12:49:50Z). The earlier reallocation (60,416 MiB with a 59,392 MiB balloon floor)
is recorded in `config/0infer/memory-hotplug/plan.json` of PR #515, which has not been merged. **Memory cannot be hot-removed**: going back down needs a clean Postgres stop, a VM shutdown, `qm set 701 --memory <MiB>` and
a start (the maintenance PR #515 describes), so this is a one-way change in practice. This directory does not set it: VM701 is a 0infer guest that is not in this repository's guest inventory (hostconf only knows it
as `vm: {hypervisor: pve-0infer, id: 701}`), so nothing in git declares or overrides its memory. It is recorded so that the next `qm set 701` starts from 66,560 MiB knowing it is deliberate.

Budget with the 64.9 GiB guest (GiB, worst plausible, no swap): 24.6 segment + 10.0 DSM cap + 5.3 page tables (14-day maximum) + 12.0 anonymous memory (14-day maximum) + 1.5 = 53.4, headroom 11.5. With a connection storm
(340 processes x 46 MiB of page tables = 15 GiB) the headroom is 1.8: that is what huge pages (a separate change, a maintenance window) remove. At the 01:25 incident, with 58.9 GiB, 24.6 + 24.5 + 3.7 + 1.7 + 1.2 = 55.7 and the page cache was already gone.

## Install and undo

`install-vm.sh` is idempotent and was **not** run by the change that added it: on VM701 the fstab line and the 10 GiB mount are already in place, so a run there changes nothing (it prints `already as wanted`,
remounts to the same size and checks). It refuses on any other machine, and when `/dev/shm` holds more than 10 GiB (a tmpfs cannot shrink below its content).

```sh
scp config/0infer/pg-primary-memory/install-vm.sh 0infer_pg_primary:/tmp/ && ssh 0infer_pg_primary 'sudo bash /tmp/install-vm.sh [--undo]'
```

1. Backs `/etc/fstab` up to `/etc/fstab.bak-shm-<UTC time>` when it changes it (a run that changes nothing makes no backup), then adds the line above, or, when a `tmpfs /dev/shm` line exists, keeps its other options and sets `size=10G`.
2. `systemctl daemon-reload` (only after a change), then `mount -o remount,size=10G /dev/shm`. Live; Postgres keeps running and its segments stay where they are.
3. Validates with `findmnt`: the fstab entry read back by `findmnt --fstab` carries `size=10G` (otherwise the backup is restored), and the live mount has exactly 10,737,418,240 bytes.

To undo: `sudo bash /tmp/install-vm.sh --undo` removes the line (the 50 % default returns at the next boot) and remounts with `size=50%`; or put the backup of 2026-10-31 back (`/etc/fstab.bak-shm-<UTC time>`, the
exact file from before) and run `sudo mount -o remount,size=50% /dev/shm`. Undoing the cap puts the 50 %-of-RAM default back (32 GiB with the 64.9 GiB guest, more than the 24.5 GiB of the incident), so do it only together with the parallel limits.

Not here, on purpose: huge pages (`vm.nr_hugepages`, `huge_pages = on`; a restart and a sysctl file whose apply runs `sysctl -p` at once, so a separate change for a maintenance window), an alert on `/dev/shm`
use (`go-fleet-metrics-hub`), and the role settings of `domainscope_app` (the application repository).

The test is `tests/test_pg_primary_memory.py`: the installer's line and this file agree, the fstab rewrite behaves, and the two hostconf files say what the ADR says. It sources the script for its functions only and never runs it.
