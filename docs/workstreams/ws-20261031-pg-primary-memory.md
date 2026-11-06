# WS-20261031: Memory guardrails for the production Postgres VM701 after the 2026-10-31 global OOM

## Status

The first change (PR 646, branch `claude/pg-primary-memory-guardrails`, ADR 0495) is merged: it recorded two live changes that were made by hand on the morning of 2026-10-31 and prepared the reload-only guardrails as hostconf files, which were applied on 2026-11-01 (S1a 11:04Z, S1b 11:41Z).
This shard is extended by the amendment of 2026-11-02 (branch `claude/pg-primary-parallel-per-gather`, task t5, in review): see "Amendment 2026-11-02". Nothing in the amendment is applied by merging; the user decides the merge and the apply.

## Goal

On 2026-10-31 at 01:25Z the kernel OOM killer ended nine `postgres` processes on VM701 and the cluster crash-recovered for about 25 s. The memory was shared memory beyond the main segment (parallel-query dynamic shared memory on `/dev/shm`), 24.5 GiB over the 24.6 GiB segment. The goal is that the settings that bound that memory live in git, with one owner each, and that the two hand changes of that morning are written down.

## Change

- `config/hostconf/files/postgresql-parallel-guardrails.infer-pg-primary.conf` (`98-parallel-guardrails.conf`): `max_parallel_workers_per_gather = 2` (4 since the amendment of 2026-11-02), `max_parallel_workers = 12`, `temp_file_limit = 150GB`.
- `config/hostconf/files/postgresql-work-mem-guardrails.infer-pg-primary.conf` (`98-work-mem-guardrails.conf`): `work_mem = 64MB`. A separate file because it is applied 30 minutes after the first.
- Both are listed on `infer-pg-primary` in `config/hostconf/hostconf.yaml` with `pg_setting` expectations. Neither is applied by merging.
- `config/0infer/pg-primary-memory/`: README (the 10 GiB `/dev/shm` cap and the VM memory, measured numbers, undo), `install-vm.sh` (idempotent fstab line, backup, remount, `--undo`), and `tests/test_pg_primary_memory.py` (the script's line and the README agree; the fstab rewrite is tested without running the installer).
- ADR 0495 (decision, arithmetic, implementation state) and an apply-order subsection in `docs/runbooks/host-local-config.md`.

## Not in this change

Huge pages (`vm.nr_hugepages`, `huge_pages = on`): applying a sysctl file runs `sysctl -p` at once and the setting needs a restart, so it is a separate PR applied only inside a maintenance window. Role settings of `domainscope_app` (`work_mem`, `client_connection_check_interval`) belong to the application repository. Alerts belong to `go-fleet-metrics-hub`. The role split, a pooler, swap and `vm.overcommit_memory` are deferred.

## Verification

Offline only: `python3 scripts/hostconf.py check`, `tests/test_hostconf.py`, `tests/test_pg_primary_memory.py`, the repository gate. No host was contacted.

## Rollback

Close the PR before merge. After an apply: restore the `postgresql.auto.conf` backup, remove the conf.d file through hostconf in the next PR, `pg_reload_conf()`; the runbook subsection lists the order.

## Amendment 2026-11-02: `max_parallel_workers_per_gather` back to 4

The 24 h acceptance of S1 found one regression: `SELECT COUNT(*) FROM mv_domains_denormalized mv` mean 0.42 s -> 0.62 s (+48 %, 15,455 calls), parallel workers per call 3.94 -> 1.97, which is exactly `max_parallel_workers_per_gather` 4 -> 2. No `could not resize shared memory segment`, no `temp_file_limit` hit, `MemAvailable` minimum 27.6 GiB over the 24 h, no OOM. The plan's rule is that a regression reverts only its own knob.

- `postgresql-parallel-guardrails.infer-pg-primary.conf`: `max_parallel_workers_per_gather = 4`; `max_parallel_workers = 12` and `temp_file_limit = 150GB` stay, and the `work_mem` file (64MB) is untouched. Header comment, `purpose` and `expect` (`"4"`) in `hostconf.yaml` follow.
- With 12 workers at most 3 gathers of 4 run at once; one parallel hash node for the role `domainscope_app` is 128 MiB x 2 x 5 = 1.25 GiB, so 3.75 GiB of `/dev/shm` (7.5 GiB with two hash nodes per gather), under the 10 GiB cap; other roles 640 MiB per node. ADR 0495 has the dated amendment, including the limits of this arithmetic.
- Runbook: the seed value, and a short paragraph "Changing a value later" (the value is in the file now, so a plain `apply`).
- Planned: applied Tue 2026-11-03 11:03Z with one `hostconf.py apply` of the parallel file (reload only). Rollback: the file back to 2 and one more `apply`. The change is not applied by merging; until it is, `drift` reports the setting not in effect.

## Amendment 2026-11-04: temporary files are logged

`pg_stat_database` counts 612 GB of temporary files (3,540 files, 177 MB on average) since 2026-10-31; `pg_stat_statements` attributes only 3.8 GB of them (5,000 entries, 2,000+ deallocations). `postgresql-temp-files-log.infer-pg-primary` (`98-temp-files-log.conf`: `log_temp_files = 64MB`, task t6) makes each spill of 64 MB or more write its size and the `STATEMENT:` to the server log. It only logs; the setting is not in `postgresql.auto.conf`, so a plain `hostconf.py apply` works (reload only). Rollback: remove the file. Tests: `tests/test_pg_primary_temp_files_log.py`.
