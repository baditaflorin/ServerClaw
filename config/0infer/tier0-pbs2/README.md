# PBS #2 per-group retention (infer-tier0, VM704)

PBS #2 (datastore `tier0`, `/srv/pbs-datastore`) is the SECOND copy of the critical backups; PBS #1 on 0own keeps the longer history. Its store-wide prune job `prune-tier0` (keep-last 3, keep-weekly 1,
07:00 UTC) cannot treat groups differently (PBS prune jobs select by namespace only). Two groups hold most of the churn, so they get a shorter retention through the datastore's own per-group prune API:

| Group | What it is | Unique bytes per snapshot (measured 2026-10-17) |
|---|---|---|
| `0docker:vm/100` | the docker host VM (~390 containers) | 22-50 GB, 216 GB for the whole group |
| `0database:vm/100` | pg-primary (the DomainScope Postgres; a physical replica also runs on 0infer) | 34-45 GB, 264 GB for the whole group |

`pbs-group-retention --apply` (timer `pbs-group-retention.timer`, 07:05 UTC: after `prune-tier0`, before garbage collection at 07:30) prunes ONLY the groups in `/etc/pbs-group-retention.json` to their newest
`keep_last` snapshots (2). Without `--apply` it is a dry run that changes nothing. Install: `install.sh` (idempotent: validates, backs up the old config, installs, runs a dry run, enables the timer).

**Guards** (all tested in `tests/test_pbs_group_retention.py`): `keep_last` below 2 is a config error; a group with no more than `keep_last` snapshots is left alone; the datastore's own dry run must list exactly the group's
snapshots and may only delete the older unprotected ones, otherwise nothing is deleted; a group whose newest snapshot is older than `max_newest_age_h` (72) is NOT pruned and the run fails (the sync that feeds it is broken: shrinking
history then only loses options) unless the group has `"frozen": true` in the config (nothing feeds it on purpose: both VM groups are frozen since 2026-10-21, `0docker:vm/100` because its VM-level job is paused and the host is backed up file by file as `0docker:host/dockerhost-state`, `0database:vm/100` because the 0database fleet is being sunset; without the flag the age guard failed every morning and raised `PbsGroupRetentionFailed`; remove the flag when a job runs again); after a prune the newest `keep_last` snapshots must still be there. Protected snapshots are never deleted.

**Space comes back two GC cycles later**: the 24 h atime grace means chunks freed by a prune are removed by the second daily GC (07:30 UTC) after it, not the first.
What the change frees beyond what the store-wide job already frees, measured with `pbs-prune-whatif.py` (installed as `/usr/local/sbin/pbs-prune-whatif`; read-only, 6 s on this datastore: `sudo ionice -c3 pbs-prune-whatif keep-last=2:ns/0docker/vm/100 drop=ns/0own/vm/630`): about 62 GB on 2026-10-17
(the store-wide job's own next prune frees about 174 GB). The what-if script also answers "what would dropping or shortening group X free?" before anyone decides.

Metrics `pbs_group_retention_*` (textfile; `group_ok`, `snapshots`, `deleted_snapshots`, last run / last success); alerts `PbsGroupRetentionFailed`, `PbsGroupRetentionStale` (tier0-runner group of
`config/prometheus/rules/tier0-standby.yml`, loaded on both Prometheus instances). To add a group: add it to the config (by PR), `install.sh`, read the dry run.
Not changed by this tool: the sync jobs (`transfer-last 2`), `prune-tier0`, GC, any other group. 0own vm/630 (`0own-openobserve`) and vm/640 (`github-mirror`) are kept: the watchdog's `must_exist` list
names vm/630 as a guest that must have a recent PBS #2 copy.
