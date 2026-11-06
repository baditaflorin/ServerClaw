# WS-20261029: Hold a guest with a weekly vzdump job to its own freshness limit

## Status

Merged (PR 624, `a39eade5e`) and applied live on 2026-10-30 at 00:48Z; receipt `2026-10-30-pve-backup-weekly-freshness-monitoring-live-apply`. The repository version bump that carries the change is still the integration step, so `included_in_repo_version` stays null.

## Goal

CT 108 (the builder) has had a weekly vzdump job since 2026-10-28: `ct108-nightly`, `sun 03:30`, storage `own-pbs`, mode `stop` (its daily restore point is the file-level group `host/ct108-live`). `PveBackupFreshnessLow` held every guest to a fixed 30 hours since its last successful vzdump, so for CT 108 it fires 30 hours after each Sunday run and stays critical until the next run finishes: about 5.75 days of every 7, with nothing failing. On 2026-10-29 it had fired for guest 108 for ten hours (the last success was 40 hours old; the daily guests were 14 to 15 hours old).

## Where the fix belongs

The collector is not in this repository. Its source of truth is `baditaflorin/fleet-state`, `hypervisor-0docker/libexec/pve-host-health-metrics.py` with `hypervisor-0docker/systemd/pve-host-health-metrics.{service,timer}`, installed by `hypervisor-0docker/install.sh` (idempotent; it keeps the replaced file as `<name>.pre-codify-<time>`, which is where the host's `pve-host-health-metrics.py.pre-codify-20261028T162935Z` comes from). Its PR 619 (merged 2026-10-28, `b293921`) already did the producer half of this fix, and it is already installed (the live script's sha256 `a113d9d0...c4c83` equals the file on fleet-state `origin/master`, the timer runs every 5 minutes):

- a guest whose only enabled job has a weekday schedule is judged over 10 days instead of 48 hours, so its last-success value is not 0 between runs;
- every guest gets `proxmox_backup_max_age_seconds`: 129600 (36 hours) for a daily guest, 734400 (204 hours = 8.5 days) for a weekly one. On 2026-10-29 the 0mcp Prometheus holds it for all five guests: 129600 for 101, 104, 107 and 109, 734400 for 108.

The metrics hub's `ProxmoxBackupStale` and the PBS-side `PbsBackupGroupStaleWeekly` already use the weekly facts. `PveBackupFreshnessLow` was the one consumer left with a fixed number, so the fix is the rule only. No collector change and no host script install are needed.

## Change

- `config/prometheus/rules/pve-host-incident.yml`, `PveBackupFreshnessLow`: the limit is now per guest. A guest the collector marks as weekly (a published `proxmox_backup_max_age_seconds` over 48 hours) is held to that value, 8.5 days. Every other guest is held to 30 hours exactly as before: the collector's own 36 hours is not used for daily guests because it would loosen them. A last-success value of 0 (the collector saw none in its window: 48 hours, or 10 days for a weekly guest) is stale for every guest. The limit is built as `max_age > 48 h` with `or on (guest_id)` falling back to `expected_guest * 30 h`, the shape `ProxmoxBackupStale` already uses. Labels, `for: 10m`, summary and the alert name (Alertmanager's inhibit rule names it) are unchanged; the description now names both limits.
- A guest whose limit series is missing (the collector rolled back to the version before 2026-10-28, a scrape gap on that one series) is judged at 30 hours, so a missing series never loosens the alert.
- `tests/promtool/pve_backup_freshness_rules_test.yml`: a weekly guest 3 days, 7 days, 8 days and exactly 8.5 days after its run raises nothing, and 9 days after (and just past 8.5 days) it fires; a daily guest is quiet at 29 and exactly 30 hours, fires at 31 and 40 hours (so not at the collector's 36); the live data of 2026-10-29 raises nothing (the old rule fired there); a daily guest that missed its run alerts while the weekly guest 3 days after its run stays quiet; a guest never backed up (value 0) alerts, weekly or daily; a missing limit series falls back to 30 hours; another scrape job's guests (including one with the same guest id) and a guest with `expected_guest` 0 are ignored.
- `tests/test_pve_backup_freshness_rules.py`: pins the labels and delay, that every series the expression reads carries the same scrape job, the two numbers the unit tests assume (30 hours daily, over 48 hours is weekly; 30 hours equals the old fixed 108000 seconds), that the unit-test inputs use the limits the collector publishes, that both a weekly and a daily guest are covered quiet and firing, and runs `promtool check` and the unit tests when promtool is installed.

Known edge, same as for a new daily job: a weekly job that has never run has no success, so the guest alerts until its first run. Run the job once by hand when creating a weekly one.

## Verification and rollback

- `promtool check rules` (3.5.0) and `promtool test rules` pass; the pytest files that read this rule file pass (`test_pve_backup_freshness_rules.py`, `test_adopted_prometheus_rules.py`, `test_pve_host_free_space_rules.py`, `test_vzdump_guard_rules.py`: 56 tests).
- The unit tests detect the bug: against the rule on `origin/main` 15 of their checks fail. Of 16 hand-made mutants of the new rule, 15 are caught: weekly marker too low or too high, daily limit 36 or 24 hours, no default limit, the collector's limit used as is, a missing job selector (on the limit, the last success, the outer filter and the default limit: the last one fails with a duplicate-series evaluation error), `>=`, `<`, no `expected_guest == 1` filter, no explicit never-seen branch (redundant in production, where `time()` is about 1.8e9, but pinned because the unit-test clock starts at 0), `for: 30m`. The first sweep let a missing job selector on the last-success series through; the last unit test covers it now. The one survivor, `or` without `on (guest_id)` on the limit, is equivalent while both series carry the same labels, which they do (one scrape target); `on (guest_id)` is kept for explicitness, as in the hub's rule.
- Read-only against the live 0mcp Prometheus on 2026-10-29 (about 19:10Z): the old expression returns guest 108, the new one returns nothing; the per-guest limit is 108000 s (30 h) for 101, 104, 107 and 109 and 734400 s (204 h) for 108; replayed over the previous 36 hours the old expression matched guest 108 only and the new one matched nothing.
- Roll back by restoring the previous alert block; nothing else depends on it.

## Live apply

- Applied on 2026-10-30 at 00:48Z to the monitoring VM (`monitoring-lv3`) with a targeted Ansible play that installs `config/prometheus/rules/pve-host-incident.yml` (main `a39eade5e`, sha256 `15ba51a2...5b78`) with the `monitoring_vm` role's own parameters (root:prometheus, 0640), validates it with the VM's `promtool` before it replaces the live file, checks the whole Prometheus configuration and reloads with SIGHUP (no restart). The play refuses to run unless the source and the live file (the PR 584 version, sha256 `666979ef...1812`) are the pinned ones. The hypervisor needed nothing: the collector already published the limit.
- Why not `make live-apply-service service=grafana`: on 2026-10-26 it stopped at the vulnerability budget gate and at the immutable guest replacement gate and would trigger a restic backup afterwards; those gates were not re-tested today (see the receipt).
- Result: `PveBackupFreshnessLow` carries the per-guest limit, health ok, state inactive; the alert for guest 108 that had fired since about 09:30Z on 2026-10-29 cleared at the first evaluation after the reload; the limits are 30 hours for guests 101, 104, 107 and 109 and 8.5 days for 108, and no guest is over its limit; only that file and one backup copy changed in `/etc/prometheus/rules` (122 to 123 entries); a check about seven hours later found everything unchanged.
- Rollback: copy `pve-host-incident.yml.pre-weekly-vzdump-20261030T004755Z` back over `pve-host-incident.yml` and send SIGHUP to `0mcp-prometheus.service`.

## Not in this change

- The collector, its units and its install (fleet-state owns them).
- `PveBackupFailureRecent` (a failed weekly run still alerts at once, critical, for 24 hours), `PbsBackupGroupStaleWeekly`, `ProxmoxBackupStale` and the `Ct108LiveBackup*` alerts: they already cover the weekly job from other sides.
- The header comment of `fleet-backup-freshness.yml` ("Existing alerts left alone: PveBackupFreshnessLow ...") stays true.
