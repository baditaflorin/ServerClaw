# WS-20261031: Huge pages for the production Postgres VM701 (S2 of ADR 0495)

## Status

In review (branch `claude/pg-primary-hugepages`). Planned: applied in a maintenance window, planned 2026-11-04, 11:00-12:00Z (any day 11:00-13:00Z once S1c has run 24 h). Nothing is applied to VM701 by this change, and it is meant to be merged only just before the window: until the files are applied, the daily `hostconf.py drift --all` reports both of them missing.

## Goal

The shared-memory segment of VM701 (`shared_buffers` 24 GiB, 24.66 GiB in all, `shared_memory_size_in_huge_pages` 12628) sits on 4 kB pages, so every backend carries 43-48 MiB of page tables: 3.7 GiB at the 140 processes of the 2026-10-31 01:25Z OOM and about 15 GiB in the connection-storm worst case. Reserving huge pages and starting Postgres with `huge_pages = on` takes that to about 0.1 MiB per backend, makes the segment non-swappable, and costs 0.34 GiB of RAM (25.0 GiB reserved against 24.66 GiB used).

## Change

- `sysctl-postgres-hugepages.infer-pg-primary` -> `/etc/sysctl.d/91-postgres-hugepages.conf`: `vm.nr_hugepages = 12800` (172 pages = 344 MiB over the 12628 needed). `apply` runs `sysctl -p` at once, so it is applied only with Postgres stopped.
- `postgresql-huge-pages.infer-pg-primary` -> `conf.d/99-huge-pages.conf`: `huge_pages = on` (a restart setting: `apply` never restarts, and rolls the file back while the running value is still `try`; the runbook order deals with that).
- Both are listed on `infer-pg-primary`. Runbook section "Huge pages for infer-pg-primary" in `docs/runbooks/host-local-config.md` (window order, fallback, rollback) and an amendment to ADR 0495.
- Tests: `tests/test_pg_primary_memory.py` pins 12800 >= 12628, the ids, destinations and the file names the window kit uses.

## Not in this change

Applying anything, the restart itself, the window kit (it lives with the coordinator), and any change to `scripts/hostconf.py` (see the runbook for how the tool treats a restart-only setting and a short reservation).

## Verification

Offline only: `hostconf.py check`, the hostconf test files, the repository gate. No host was contacted. Behaviour of `SHOW` for a restart-only setting after a reload was checked against a throwaway local Postgres 17 cluster.

## Rollback

Close the PR before merge. After the window: the runbook's rollback (stop, `vm.nr_hugepages = 0`, `huge_pages = try`, start), then remove the two entries from `hostconf.yaml` in a PR.

## Rider: `pg_stat_statements.max` 5000 -> 20000

`postgresql-pgss-max.infer-pg-primary` (`conf.d/99-pgss-max.conf`: `pg_stat_statements.max = 20000`, task t4) is a separate PR stacked on this one. The 5,000-entry table evicts (2,000+ deallocations since 2026-10-31) and attributes only 3.8 GB of the 612 GB of temporary files, so the next 24 h of attribution need the larger table. It is a restart setting of a preloaded library: it rides on the restart of this window, costs about 6 MB of shared memory (about 3 of the 172 spare huge pages), and follows the same order as `huge_pages` (seeded with `ALTER SYSTEM` before the stop, applied after the start, then reset), because `apply` before the restart reads 5000 and exits 5. The runbook section covers both settings; one restore of the `postgresql.auto.conf` backup is the fallback for both.
