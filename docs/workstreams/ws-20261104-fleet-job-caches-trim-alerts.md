# WS-20261104: alerts for the build VM's Go build cache trim (step 3d)

## Status

Merged (PR 672, `03cc038fe`, ADR 0494 as for the other VM 130 work) and applied live on 2026-11-04 at 21:30Z; receipt `2026-11-04-fleet-job-caches-trim-alerts-monitoring-live-apply`. The rule file, tests and docs were written and reviewed in git only (PR 672 changed no host); copying the file to the monitoring VM was a separate step on the owner's yes.

## Goal

Step 3d of the 4-hourly GC on the CI build VM (`docker-build-lv3`, VM 130 on 0mcp; platform_server PRs 657 and 664) trims the Go build cache inside the `fleet-job-cache-*` volumes to a 20 GiB cap and, at the end of every full run, writes `fleet_job_caches_trim.prom` into node_exporter's textfile directory. That trim is what keeps the VM's root off the disk-full line: the go-url-categorizer-api cache grew from 17 to 80 GiB in two days before it existed, and on 2026-11-02 the step would have been skipped silently (its helper image had been pruned). No rule on either Prometheus reads the file. This change adds the alerts that do: the last run failed or was skipped, no run for 9 hours, no metric at all, and a volume over its cap for a day.

## Evidence (read-only, 2026-11-03 22:55Z to 23:20Z)

- **Nothing alerted on it.** `fleet-prom rules --json` of the 0mcp and the 0docker Prometheus: 0 rules that mention `fleet_job_caches_trim` or `FleetJobCaches`; `git grep` on origin/main finds the metric only in the wrapper script, its tests and the README.
- **The series.** The 0mcp Prometheus holds all four gauges with `host="docker-build-lv3"`, `instance="10.10.10.30:9100"`, `fleet="0mcp"`, scraped every 30 s (20 samples in 10 minutes). The 0docker one shows the same file as `host="0mcp-builder"`. The first run that wrote the file was 2026-11-03 12:25:20Z, so the series is less than 11 hours old: three runs, at 12:25:20, 16:27:47 and 20:27:44Z (4 h 02 m 27 s and 3 h 59 m 57 s apart), `last_result` 0 every time, `volumes_over_cap` 0 every time, freed 29,286, 2,722 and 3,303 MiB. The age of the file (`time()` minus the run time) never went above 14,560 s (4 h 02 m 40 s) in those 11 hours, and was 9,790 s at 23:10Z.
- **The four expressions of the rule file, evaluated as instant queries on the live Prometheus at 23:10Z, return nothing**: applying the file fires none of them today.
- **The exporter's own gauges agree:** `up` 1, `node_textfile_scrape_error` 0, and `node_textfile_mtime_seconds` for the file equals the last run's time.
- **The timer and the unit** (files in this directory): `OnCalendar=*-*-* 00/4:23`, `RandomizedDelaySec=300`, `Persistent=true`; the service runs `flock -n /run/lock/docker-build-gc.lock docker-build-gc.sh` with `TimeoutStartSec=2h`; step 3d is `timeout 1800 .../fleet-job-caches-trim.sh | tail -12`, so a run that the timeout kills writes no file and a run with many changed volumes shows only its last 12 lines in the journal.
- **Routing** (`config/alertmanager/alertmanager.yml` on origin/main, not read from the live Alertmanager): `critical` goes to the ntfy critical topic, `warning` to the ntfy warning topic (first notice after 5 minutes, repeated every 12 hours while it fires, no resolved message), `info` to the null receiver.
- **How long a burst lasts** (root filesystem of the VM, 10 days, 1 hour steps; the over-cap flag itself did not exist before 11-03): the one rise that ran longer than a day was 2026-10-29 to 10-31 (70.9 % used on 10-30 05:11Z, 94.2 % on 10-31 11:11Z), before the trim existed; the other days show a rise of 8 to 12 points within a day that then falls.

## Change

- `config/prometheus/rules/fleet-job-caches-trim.yml`: group `fleet_job_caches_trim`, `max by (host)` over series of `host="docker-build-lv3"`, label `service: fleet_job_caches_trim`, runbook anchor in `docs/runbooks/fleet-observability.md`:
  - `FleetJobCachesTrimFailed` (warning): `last_result != 0` for 1 hour.
  - `FleetJobCachesTrimStale` (warning): `time() - last_run_timestamp_seconds > 9 * 3600` for 30 minutes.
  - `FleetJobCachesTrimMissing` (warning): `absent(last_run_timestamp_seconds{host="docker-build-lv3"})` for 1 day.
  - `FleetJobCachesOverCap` (info): `volumes_over_cap > 0` for 24 hours.
- `tests/promtool/fleet_job_caches_trim_rules_test.yml` (12 test groups: each alert's before, at and after the delay, a duplicate series, another host's series, a vanishing file, one missed run against two) and `tests/test_fleet_job_caches_trim_rules.py` (runs promtool where it is installed; pins the expressions, severities, delays and labels; that the rules read only gauges the wrapper script writes; that the delays follow the GC timer's period; that the texts name files and units that exist and use `sudo -n journalctl`; that the runbook and the README describe each alert). The test is a separate line of the Woodpecker pytest step.
- `config/0mcp/docker-build-lv3/README.md`: a subsection "Alerts on the trim" (what each alert means, what to do, the kill switch and its effect), and one sentence of "The image" that said an alert was not in that change.
- `docs/runbooks/fleet-observability.md`: a section "Build host cache trim alerts" and a rollback row.
- The rule file is in `monitoring_prometheus_adopted_rule_files` (role `monitoring_vm`) and in the pinned list of `tests/test_adopted_prometheus_rules.py`.

## Decisions

- **A separate rule file, not shared with PR 660's `fleet-ci-cache-prune.yml`.** Different host, metric family, cadence and owner, and PR 660 is inert until its own host script ships while this file is ready to ship: one file would tie the two apply steps together. The two PRs still both change the generated registry and coordination diagram (whichever merges second regenerates them); the lists they both extend (adopted rule files, its pinned copy in the test) and the Woodpecker pytest step are edited at different places so that they merge without a conflict.
- **`FleetJobCachesOverCap` is `info`.** In a CI burst the flag is above 0 for hours by design (the 12 hour floor for a volume in use beats the 20 GiB cap, the hot volume peaks at 35 to 45 GiB), so a short delay is noise; with the delay at a day it is a tuning signal (the cap and the floor no longer fit the load), and the real danger, a full root disk, already has `FleetRootFilesystemLow` and `FleetRootFilesystemCritical`. A `warning` would re-notify every 12 hours for as long as a burst lasts, on a host that already has warnings firing. One word changes it.
- **`FleetJobCachesTrimFailed` fires on a single bad run (delay 1 hour).** A bad value stays up to 4 hours, so any delay up to 4 hours means "one bad run". The alternative is 5 hours (two bad runs in a row, the model the README sketched before); it is a tuning choice that waits for evidence about how often a single run fails and heals.
- **Stale is 9 hours + 30 minutes.** Observed age never above 4 h 03 m; one missed run peaks near 8 h 05 m (arithmetic from the two observed gaps), two missed runs cross 9 hours before the third run is due.
- **Missing waits a day** (six runs): a file that vanishes or a node_exporter that stops is rarely worth a notification inside the first hours, and `up` alerts exist for the exporter itself.
- **The rules name the host.** Their numbers are this host's timer. A second host that gets the wrapper needs its own copy with its own delays; the header of the rule file says so.

## Predicted, not observed

No alert has ever fired on this metric, and no run has ever failed, been skipped or ended over its cap, so every delay is reasoning checked against 11 hours of healthy history, not a back-test. In particular: that a single failed run is rare enough for `Failed` to be quiet; that `OverCap` stays quiet in ordinary working days and fires in a multi-day burst like 10-29 to 10-31 (read from the root-filesystem series, not from the flag); that the kill switch (`chmod -x` on the wrapper) makes `Stale` fire about 9 h 30 m later (the file keeps the last run's time).

## Not in this change

- Nothing is applied: no file on the monitoring VM, no reload, no change on `docker-build-lv3`. The VM's own `promtool` (Prometheus 2.53.3 there, 3.5.0 on the authoring Mac) was not run; the rules use only `max by`, `time()`, `absent` and comparison.
- No alert on `fleet_job_caches_trim_freed_bytes` (a night run that frees nothing is normal), none for the other textfile jobs of the host.
- The staged plan in the README still says step 4 "has not been" applied and its section title says "NOT installed", although step 4 was applied on 2026-11-03 10:05Z: left as it is, the new subsection says so (a follow-up).

## Verification

Offline. `promtool check rules` and `promtool test rules` (promtool 3.5.0) pass; `tests/test_fleet_job_caches_trim_rules.py`, `tests/test_adopted_prometheus_rules.py`, `tests/test_docker_build_lv3_config.py`, `tests/test_docker_build_gc_cache_trim.py` and `tests/test_monitoring_prometheus_codification.py` pass. A sweep of 88 one-change mutations on scratch copies (a threshold, a delay, a label, a metric name, the host selector, an annotation, an alert name, the role entry, a docs heading or row, a fact in the wrapper script or the timer) killed all 88: 68 of the 69 changes to the rule file fail a promtool unit test, the 69th (a fifth alert added) fails the pin in the pytest wrapper, and the 19 changes to the role entry, the docs, the wrapper script and the timer fail the pytest wrapper. Then the repository pre-push gate on the build server (the pull request records the result).

## Rollback

Revert the commit of PR 672, and remove the live rule file: `ssh 0mcp_monitoring 'sudo rm /etc/prometheus/rules/fleet-job-caches-trim.yml && sudo systemctl kill --kill-whom=main --signal=HUP 0mcp-prometheus.service'` (the file did not exist on the VM before, so there is no backup copy). Remove the name from `monitoring_prometheus_adopted_rule_files` too, so that a converge does not put the file back.

## Live apply

- Applied on 2026-11-04 at 21:30Z to the monitoring VM (`monitoring-lv3`) with a targeted Ansible play that installs `config/prometheus/rules/fleet-job-caches-trim.yml` (sha256 `9ae9af42...6f40`, main `03cc038fe`) with the `monitoring_vm` role's own parameters (root:prometheus, 0640, validated by the VM's promtool 2.53.3 first), checks the whole Prometheus configuration, reloads with SIGHUP (no restart) and reads the group back. Check mode first: one new file and nothing else. Not a converge: `make converge-monitoring` replays every adopted rule file.
- Result: group `fleet_job_caches_trim` (4 rules) is loaded, every rule health ok and state inactive, lastError none; Prometheus went from 70 groups and 564 rules to 71 and 568. The four expressions returned nothing before and after (last result 0, age of the metric file 3,839 s, no volume over its cap), so nothing fires; the 26 alerts that were firing are the same 26 after. The listing of `/etc/prometheus/rules` differs by exactly one line (127 to 128 entries); all 39 other `.yml` files were already loaded, so the reload took in nothing else.
- Rollback: see above. Receipt: `2026-11-04-fleet-job-caches-trim-alerts-monitoring-live-apply`. `platform_version` 0.179.55 to 0.179.56.
