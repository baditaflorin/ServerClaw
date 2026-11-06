# ADR 0495: The production Postgres VM701 bounds the shared memory its parallel queries can take

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: partly live since 2026-10-31 (the `/dev/shm` cap at 08:02Z and the VM memory at about 08:17Z, both by hand, before this ADR); the two Postgres files were applied on 2026-11-01 (S1a 11:04Z, S1b 11:41Z); the per-gather limit restored by the amendment of 2026-11-02 is planned for Tue 2026-11-03 11:03Z
- Date: 2026-10-31
- Concern: resilience
- Tags: postgres, oom, shared-memory, parallel-query, hostconf, infer-pg-primary

## Context

On 2026-10-31 at 01:25Z the kernel OOM killer ended nine `postgres` processes on VM701 (`infer-pg-primary`, the production DomainScope Postgres 18 on the 0infer hypervisor) and the cluster crash-recovered for about 25 s. The postmaster survived
(`oom_score_adj` -900); any killed child of it crashes the cluster, so no score avoids the recovery.

What is proven (kernel report and metrics): the memory that ran the VM out was **shared memory beyond the main segment**. The segment was a constant 24.62 GiB (`shared_buffers` 24 GiB); the kernel's report at 01:25:18 says `shmem` 49.1 GiB, an excess of
+18.3 GiB at the 01:24:00 scrape and +24.5 GiB at the kill, inside one 30 s scrape interval. It was not `/tmp` (0.1 MiB used) and not a connection burst by itself. The only other tmpfs user of Postgres is dynamic shared memory (DSM, on `/dev/shm`, 30 GiB at the time:
the tmpfs default of 50 % of RAM), so the excess was parallel-query memory. In the six days of log before it the DSM excess never passed +4.1 GiB (+8.1 GiB on 2026-10-21 in the 14-day series): the incident was three to six times anything seen.
What is **not** known: which statement made the 24.5 GiB (killed statements never log and `pg_stat_statements` was reset by the crash). The settings explain the size, they do not name a query.

The settings allowed it. `max_parallel_workers` 24 with 4 workers per gather is 6 simultaneous gathers, and one parallel hash node may use `work_mem x hash_mem_multiplier x (workers + 1)`:

| | work_mem | multiplier | participants | per node | 6 gathers |
|---|---|---|---|---|---|
| role `domainscope_app` (the application's login, `work_mem` set on the role) | 512 MB | 2 | 4 + 1 | 5.0 GiB | **30 GiB** |
| every other role (global) | 256 MB | 2 | 4 + 1 | 2.5 GiB | 15 GiB |

30 GiB against 24.5 GiB seen is an arithmetic ceiling that matches the size, not an observation of a query.

Two changes were made by hand that morning, by two other sessions, and are in no repository: `/dev/shm` capped at 10 GiB (08:02Z) and the VM raised from 60,416 to 66,560 MiB by hotplug (about 08:17Z). The parallel limits (`max_parallel_workers_per_gather`
4, `max_parallel_workers` 24) and the global `work_mem` (256MB) are `ALTER SYSTEM` values in `postgresql.auto.conf` (plan, section 6), which overrides every `conf.d` file and is in no repository either; `temp_file_limit` is at its default of -1 and
probably not in that file (the runbook looks at `pg_settings.source` first and treats all three names the same either way).

The incident note and the plan with the evidence are on the operator's laptop, outside this repository: `fleet_agent_primitives/sessions/2026-10-31-pg-primary-oom/README.md` and `fleet_agent_primitives/sessions/2026-10-31-pg-primary-oom/PLAN.md` (the pre-change baseline is in `evidence/baseline-pgss-20261031T0832Z.txt` of the same folder).

## Decision

1. **Keep the 10 GiB `/dev/shm` cap and the 66,560 MiB of VM memory (no ballooning), and record both** in `config/0infer/pg-primary-memory/` (README with the measured numbers and the undo, `install-vm.sh` idempotent for the fstab line, a test). 10 GiB is above every DSM figure seen
   (+8.1 GiB at most) and far below the incident's 24.5 GiB: a query that needs more fails alone with `could not resize shared memory segment` instead of the cluster crashing. Not tested on this build: a query over the cap; the failure mode is documented Postgres behaviour.
2. **Cut what feeds the DSM, as two reload-only hostconf files** (`config/hostconf/hostconf.yaml`, host `infer-pg-primary`, `pg_setting` expectations, mode 0640 group `postgres`), applied 30 minutes apart so that a regression is attributable to one knob:
   - `postgresql-parallel-guardrails.infer-pg-primary` -> `conf.d/98-parallel-guardrails.conf`: `max_parallel_workers_per_gather = 4` (first decided as 2; restored to 4 by the amendment of 2026-11-02), `max_parallel_workers = 12`, `temp_file_limit = 150GB`. At most 3 gathers of 4 workers run at once (12 / 4; 6 gathers of 2 as first decided). `temp_file_limit` bounds
     what one process may spill to the data disk once `work_mem` is lower (1.5 TB free, 34 % used; 2.1 GB of temp files since 01:25Z, so spills are rare today).
   - `postgresql-work-mem-guardrails.infer-pg-primary` -> `conf.d/98-work-mem-guardrails.conf`: `work_mem = 64MB`. `hash_mem_multiplier` stays 2 and `jit = off` stays.
3. **The application's role settings are not part of this repository's change** and complete the arithmetic: `domainscope_app` `work_mem` 512MB -> 128MB and `client_connection_check_interval = '10s'` (a statement whose client has gone ends and releases its memory) belong to the application repository
   (an idempotent script there). Until the role is changed the role keeps 512 MB and the ceiling below is not reached; this change does not claim it is.
4. **Apply order** is in `docs/runbooks/host-local-config.md` ("Postgres settings that `postgresql.auto.conf` shadows"): back up `postgresql.auto.conf`, seed it with the new values and reload, `hostconf.py apply` the file, `ALTER SYSTEM RESET` the names, reload, check `pg_settings.sourcefile`.
   The runbook does not write the file first and reset afterwards: `hostconf.py apply` reads each `expect` back with `SHOW` and rolls the file back (exit 5) when the live value is still the shadowing one.
5. **Not in this decision**: alerts on DSM use and on `MemAvailable`
   (`go-fleet-metrics-hub`), `statement_timeout` for the shared role (needs the role split first: the role is used by the api, cron and a backfill, and the longest legitimate statement seen is 868 s), a connection pooler, a guest swapfile, `vm.overcommit_memory`,
   and the 24.6 GiB `shared_buffers`. Each has its own step and rollback in the plan.
6. **Huge pages (S2, amendment of 2026-10-31; planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h))**: `vm.nr_hugepages = 12800` and `huge_pages = on`, as two more hostconf files on `infer-pg-primary`
   (`sysctl-postgres-hugepages.infer-pg-primary` -> `/etc/sysctl.d/91-postgres-hugepages.conf`, `postgresql-huge-pages.infer-pg-primary` -> `conf.d/99-huge-pages.conf`), one restart, in its own PR that is merged only just before the window. See "Huge pages (S2)" below.

### The arithmetic after the change (as first decided, 2 workers per gather; the current figures are in the amendment of 2026-11-02)

| | work_mem | multiplier | participants | per node | 6 gathers (12 / 2) |
|---|---|---|---|---|---|
| role `domainscope_app` once its role setting is 128 MB | 128 MB | 2 | 2 + 1 | 768 MB = 0.75 GiB | **4.5 GiB** (9 GiB if every gather had two hash nodes) |
| every other role (this change: global 64 MB) | 64 MB | 2 | 2 + 1 | 384 MB | 2.25 GiB |

Both rows stay under the 10 GiB cap, which then stays as the backstop and not as a design figure. Budget with the 64.9 GiB guest (GiB, worst plausible, no swap): 24.6 segment + 4.5 designed DSM + 5.3 page tables (14-day maximum)
+ 12.0 anonymous memory (14-day maximum) + 1.5 = 47.9, headroom 17.0; with the cap used in full (10.0 instead of 4.5) 53.4 and headroom 11.5, and with the cap used in full and a connection storm (340 processes x 46 MiB of page tables = 15 GiB) 1.8, until huge pages remove the page tables.

### Acceptance (48 h after the last file is applied, read from `pg_stat_statements` against the baseline)

No top-15 statement's `mean_exec_time` more than 25 % above baseline (the `LIKE` family 3.2 s and 5.4 s, `COUNT(*)` of the materialised view 0.4 s); `temp_bytes` growth under 50 GB a day; no `could not resize shared memory segment`, or, if some, the statement they name is known;
`MemAvailable` minimum above 20 GiB; Shmem excess over baseline under 8 GiB. A regression reverts only its own knob: the parallel file first, then `work_mem`.

### Huge pages (S2), planned

S1 was applied on 2026-11-01 with one regression (`max_parallel_workers_per_gather`), fixed by #658 (S1c) on 2026-11-03; S2 follows 24 h later: planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h).

| | |
|---|---|
| Segment | `shared_memory_size_in_huge_pages` 12,628 pages of 2 MiB = 24.66 GiB; 12,800 pages reserved = 25.0 GiB, a margin of 172 pages = 344 MiB; net RAM cost +0.34 GiB; the segment becomes non-swappable |
| Page tables | 43-48 MiB per backend become about 0.1 MiB: 3.7 GiB at the 140 processes of 2026-10-31 01:25Z become about 0.02 GiB; the worst case (`max_connections` 300, 24 workers, about 14 auxiliary processes, the settings of that day) about 15 GiB becomes about 0.03 GiB |
| Cost | one restart: 5 s measured on 2026-10-30 after a manual `CHECKPOINT`, a 60 s budget for the outage; planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h), after the two S1 files have run for 24 h |
| Preconditions | `huge_pages` is `try`, `HugePages_Total` 0, 12,628 still the figure, `MemAvailable` above 25 GiB, no base backup or rehearsal running, balloon equal to memory (ballooning stays off while pages are reserved) |

Why Postgres is stopped before the pages are reserved: only about 0.2 GiB of free blocks of 2 MiB or larger exist (`/proc/buddyinfo`), so reserving while it runs counts the resident 24.6 GiB segment twice and evicts about 25 GiB of page cache of an I/O-bound 654 GB database;
stopped, the freed segment is the source. Two behaviours of `hostconf.py`, checked in its code and on a throwaway Postgres 17 cluster, shape the order (the runbook, "Huge pages for infer-pg-primary", has the steps):

- Applying a sysctl file runs `sysctl -p` at once, and a reservation of fewer than 12,800 pages is "not in effect" to the tool: it puts the file and the old page count back and exits 5. A short reservation therefore ends as no reservation, not as a partial one.
- `huge_pages` is a restart setting: after a reload `SHOW` still says `try` (`pending_restart` is true), so `apply` of `99-huge-pages.conf` while the server runs on `try` is rolled back (exit 5). The order seeds `ALTER SYSTEM SET huge_pages = 'on'` before the stop (it changes nothing until the restart) and applies the file after the start, when `SHOW` says `on`, then resets the `ALTER SYSTEM` value.

Fallback if the reservation is short after one compaction retry: start with `huge_pages = try` (restore the `postgresql.auto.conf` backup), keep the files out, and reserve at a later reboot with the kernel parameter `hugepages=12800`. Rollback: stop, `vm.nr_hugepages = 0`, `huge_pages = try`, start (about 30 s).
Acceptance: `SHOW huge_pages` is `on`, `HugePages_Free` about 172, `PageTables` under 0.5 GiB, outage within 60 s, `pg_is_in_recovery()` false, the public health endpoint 200, the replica streaming, `hostconf.py drift --host infer-pg-primary` exit 0.

**Rider: `pg_stat_statements.max` 5,000 -> 20,000** (`postgresql-pgss-max.infer-pg-primary` -> `conf.d/99-pgss-max.conf`, `pg_stat_statements.max = 20000`). It is a restart setting, so it rides on the same restart. The table of 5,000 entries evicts (2,000+ deallocations since 2026-10-31) and attributes only 3.8 GB of the 612 GB of temporary files that `pg_stat_database` counts, so the next 24 h of attribution have to be complete. Cost: about 6 MB of shared memory (Postgres 17: `shared_memory_size` 146 MB -> 152 MB), about 3 of the 172 spare huge pages, so `HugePages_Free` after the start is about 169 instead of 172. A clean shutdown keeps the statistics file.
Checked on a throwaway Postgres 17 cluster with the library preloaded: `ALTER SYSTEM SET pg_stat_statements.max = 20000` is accepted for the extension setting; `SHOW` stays 5000 and, after a reload, `pending_restart` is true (`pg_file_settings` shows 20000, `applied` false); after a fast restart `SHOW` says 20000 and the same 14 entries are there; after `ALTER SYSTEM RESET` and a reload the value comes from the conf.d file and `pending_restart` is false. So `apply` of the file before the restart reads 5000 and exits 5, as for `huge_pages`: the window order seeds both values before the stop, applies both files after the start and resets both, and the one restore of the `postgresql.auto.conf` backup is the fallback for both (the rider then waits for the next restart).

## Implementation state

| Piece | State | Where it lives |
|---|---|---|
| `/dev/shm` 10 GiB | **live** since 2026-10-31 08:02Z (fstab line + remount, by hand); this change makes it repeatable and recorded; `install-vm.sh` was not run (it would change nothing there) | `config/0infer/pg-primary-memory/` |
| VM 701 memory 66,560 MiB, balloon 66,560 | **live** since about 08:17Z (hotplug, by hand); memory cannot be hot-removed; recorded, not set by git | `config/0infer/pg-primary-memory/README.md` |
| `98-parallel-guardrails.conf` | **applied** 2026-11-01 11:04Z (S1a); `max_parallel_workers_per_gather` goes back to 4 by the amendment of 2026-11-02, **planned: applied 2026-11-03 11:03Z** | `config/hostconf/` |
| `98-work-mem-guardrails.conf` | **applied** 2026-11-01 11:41Z (S1b), `work_mem` 64MB, unchanged by the amendment | `config/hostconf/` |
| role `domainscope_app` settings | not started here | the application repository |
| huge pages (`91-postgres-hugepages.conf`, `99-huge-pages.conf`) | **planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h)**; the files are in git from their own PR (merged just before the window), nothing is applied by merging | `config/hostconf/`, runbook `docs/runbooks/host-local-config.md` |
| `pg_stat_statements.max` 20000 (`99-pgss-max.conf`) | **planned with S2** (restart-only rider on the same restart); in git from its own PR stacked on the S2 PR, nothing is applied by merging | `config/hostconf/`, runbook `docs/runbooks/host-local-config.md` |
| alerts, role split | not started | separate changes |

Both files were applied on 2026-11-01 (S1a 11:04Z, S1b 11:41Z); the 24 h acceptance and the one revert are in the amendment of 2026-11-02. The repo version and platform version
that first describe the applied state are recorded when the apply is done (AGENTS.md rules 12 and 17): this ADR then moves to Implemented, with the receipt.

## Consequences

- Parallel scans are slower where they are CPU-bound; the load average of VM701 is 6-8 on 32 vCPUs and the data disk is the bottleneck, so the cost is expected to be small. The acceptance rule is the check.
- A hash join that outgrows 64 MB spills to the data disk, which is already the bottleneck; `temp_file_limit` keeps one process from filling it.
- A single `domainscope_app` client can still spend the 10 GiB and make other parallel queries fail (availability, not a crash). The real fix is splitting the shared role (api, cron, backfill), a later step.
- Settings that live in `postgresql.auto.conf` and are not listed here (27, per `config/hostconf/README.md`: `shared_buffers`, `max_connections`, the WAL sizes ...) stay known drift; moving them needs the owner to say which side is right.

## Rollback

Per file and per knob, fastest first: `ALTER SYSTEM SET` the old values back (they beat the file and take effect on `pg_reload_conf()`) or restore the `postgresql.auto.conf` backup taken before the apply. The file itself is removed from `hostconf.yaml` in a PR and from the host by hand
(hostconf never deletes). The cap: `install-vm.sh --undo`. The VM memory: a clean stop and `qm set 701 --memory <MiB>` (not hot-removable). Closing the PR before merge changes nothing anywhere.

## Amendment 2026-11-02: `max_parallel_workers_per_gather` goes back to 4

**State: planned, applied Tue 2026-11-03 11:03Z** (one reload-only `hostconf.py apply` of the parallel file). S1 itself was applied live on 2026-11-01: S1a, the parallel file, at 11:04Z; S1b, the `work_mem` file, at 11:41Z.

**Acceptance result (24 h, against the baseline).** One regression: `SELECT COUNT(*) FROM mv_domains_denormalized mv`, mean 0.42 s -> 0.62 s (+48 %, 15,455 calls; the rule allows 25 %), parallel workers per call 3.94 -> 1.97, which is exactly `max_parallel_workers_per_gather` 4 -> 2.
Everything else held: no `could not resize shared memory segment`, no `temp_file_limit` hit, `MemAvailable` on VM701 never below 27.6 GiB in the 24 h, no OOM.

**Decision.** The acceptance rule applies: a regression reverts only its own knob. `max_parallel_workers_per_gather = 4` again. `max_parallel_workers = 12`, `temp_file_limit = 150GB` and the `work_mem` file (64MB) stay.

**Arithmetic (binary units).** With `max_parallel_workers = 12` at most 3 gathers of 4 workers run at once (12 / 4). One parallel hash node is at most `work_mem x hash_mem_multiplier x (workers + 1)`:

| | work_mem | multiplier | participants | per node | 3 gathers |
|---|---|---|---|---|---|
| role `domainscope_app` at its 128 MiB role setting | 128 MiB | 2 | 4 + 1 | 1280 MiB = 1.25 GiB | **3.75 GiB** of `/dev/shm` (7.5 GiB if every gather has two hash nodes) |
| every other role (global 64 MiB) | 64 MiB | 2 | 4 + 1 | 640 MiB | 1.875 GiB |

Both stay under the 10 GiB cap. For comparison: before S1, 6 gathers x 5.0 GiB = 30 GiB; as first decided (2 per gather), 4.5 GiB; the incident, 24.5 GiB.

**Limits of this arithmetic (not verified).** Three is the number of fully staffed gathers. The budget of a node follows from the workers planned for it, and workers launched can be fewer, so a query that finds the worker pool empty may still hold a node of the same budget: the true ceiling is the number of concurrent parallel hash joins x 1.25 GiB,
and the cap is what holds it (8 nodes of 1.25 GiB are the 10 GiB). The 1.25 GiB also assumes the 128 MiB role setting, which belongs to the application repository and was not checked here: at the old 512 MiB a node is 5 GiB and three of them 15 GiB.

**Apply and check.** The S1 apply moved the value into the file, so nothing shadows it and this is a plain `python3 scripts/hostconf.py apply --host infer-pg-primary --file postgresql-parallel-guardrails.infer-pg-primary --yes` (look at `pg_settings.source` first; if it still names `postgresql.auto.conf`, use the order in the runbook).
The same 48 h comparison applies: the `COUNT(*)` statement back near 0.42 s with about 3.9 workers per call, `MemAvailable`, the Shmem excess over baseline, no `could not resize shared memory segment`. Rollback of this knob: the file back to 2 and one more `apply`.

## Amendment 2026-11-04: temporary files are logged (`log_temp_files = 64MB`)

**State: planned, applied after the merge with one reload-only `hostconf.py apply`** (no restart, no maintenance window needed).

**Why.** `pg_stat_database` shows 612 GB of temporary files (3,540 files, 177 MB on average) since 2026-10-31, but `pg_stat_statements` attributes only 3.8 GB of them: its table holds 5,000 entries and evicts (more than 2,000 deallocations), so the statements behind the spills are not known,
and the `work_mem` and `temp_file_limit` decisions above cannot be judged against them. The server log can name them: `log_temp_files = 64MB` writes one line per temporary file of 64 MB or more with its size, and the `STATEMENT:` that wrote it.

**Decision.** One more hostconf file on `infer-pg-primary`: `postgresql-temp-files-log.infer-pg-primary` -> `conf.d/98-temp-files-log.conf` (0640, group `postgres`), `log_temp_files = 64MB`, `expect` `log_temp_files` = `64MB`.
It logs only; no query changes behaviour. Checked on a throwaway Postgres 17 cluster: `SHOW` prints `64MB`, the setting is a superuser setting (reload, no restart), a 131 MB spill wrote `temporary file: path "...", size 131088384` followed by its `STATEMENT:`, and a 12 MB spill wrote nothing although `pg_stat_database` counted it.
The limit is per file: a query that leaves several files each under 64 MB is not logged (the average file is 177 MB). Expected volume (an estimate): about ten lines an hour at the recent 1.9 GB an hour, about 34 at the average of about 6 GB an hour since 2026-10-31 (612 GB and 3,540 files in 104 h), hundreds in a busy evening.

**Apply and check.** `log_temp_files` is -1 (the default) and not in `postgresql.auto.conf`, so nothing shadows the file: a plain `python3 scripts/hostconf.py apply --host infer-pg-primary --file postgresql-temp-files-log.infer-pg-primary --yes` (look at `pg_settings.source` first; if it names `postgresql.auto.conf`, use the order in the runbook).
Then read the log for `temporary file:` lines and match each `STATEMENT:` to the statements of the acceptance baseline. Rollback: remove the file (hostconf never deletes; remove it by hand and the entry in a PR); the default -1 is back at the next reload.
