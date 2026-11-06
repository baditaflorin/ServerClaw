# DomainScope search probe (CT108, every 15 minutes)

Why this exists. On 2026-10-20 production DomainScope semantic search answered 500 to every uncached query for hours and country-scoped smart
search answered 0 rows, while every route-level check (health, version, edge probe, post-deploy smoke) passed: nothing looked at what search
*answered*. The DomainScope repository now carries its own probe, `scripts/search-probe.sh` with golden queries in
`scripts/search-golden-queries.tsv` (baditaflorin/go-url-categorizer-api); this job runs it on a schedule and alerts when it fails.

## What runs where

| Piece | Where | What it does |
|---|---|---|
| `domainscope-search-probe.timer` | CT108 (`config/systemd/`) | every 15 minutes at :04/:19/:34/:49 (+ up to 60 s), no catch-up run after a boot |
| `domainscope-search-probe.service` | CT108 | `flock -n` + the wrapper; exit 2 (a search check failed) is a success of the unit, exit 3 is a failed unit |
| `/usr/local/bin/domainscope-search-probe-run` | CT108 (`scripts/domainscope-search-probe-run`) | fetches the probe from origin/main (blobless depth-1 clone in `/var/lib/domainscope-search-probe/repo`, only the four files the probe reads are extracted), runs `search-probe.sh --all --markets 20 --metrics-file ... https://domainscope.scrapetheworld.org` **as `nobody` with an empty environment**, then installs the metrics file |
| `domainscope_search_probe.prom` | CT108 `/var/lib/prometheus-node-exporter/textfile/` | read by the builder's node exporter, scraped by the 0mcp Prometheus (`instance="100.114.37.21:9100"`, `host="0docker-builder"`) |
| `config/prometheus/rules/domainscope-search.yml` | monitoring VM `/etc/prometheus/rules/` | `DomainScopeSearchBroken`, `DomainScopeSearchProbeStale` (severity warning: Alertmanager sends them to the ntfy warning topic and to fleet triage) |

The probe only reads: about 46 anonymous GET requests to `/api/v1/search/smart` and `/api/v1/search/semantic` per run (the uncached semantic
query, the golden queries, 20 random `/markets` cells), about 4.5 minutes. That is half the anonymous LLM-search budget of 90 requests per
10 minutes per address, and only one run falls into any 10 minutes. Each run asks one semantic query nobody asked before, so production embeds
it: one paid embedding call per run (about 96 a day), by design, because the 2026-10-20 outage hit exactly that path. Smart-search briefs are
cached by the API after their first parse, so the 384 market cells cost one LLM parse each, once.

### Metrics

Written by the probe (`--metrics-file`, atomic temp file + rename), every series with `target="<base url>"`:

| Metric | Meaning |
|---|---|
| `domainscope_search_probe_success` | 1 when the run finished and every gating check passed, else 0 |
| `domainscope_search_probe_failed_checks` | gating checks that failed (an error that stopped the probe counts as one) |
| `domainscope_search_probe_checks_total` | gating checks run (about 45) |
| `domainscope_search_probe_known_failing_checks` / `_known_failing_failed_checks` | golden queries gated `known-failing` (a known gap with a follow-up): run and reported, never failing the probe |
| `domainscope_search_probe_duration_seconds` | wall time of the run |
| `domainscope_search_probe_last_run_timestamp_seconds` | end of the run |

A run that leaves no valid metrics (the probe crashed, ran past 12 minutes, or wrote lines of other families) is recorded by the wrapper as a
failed run: the same families with `success 0`, `failed_checks 1`. A failed fetch of the repository runs the last probe fetched (production is
still checked); with no earlier probe nothing is written and the stale alert covers it.

## The alerts

- **`DomainScopeSearchBroken`**: no run in the last 20 minutes succeeded and at least two runs ended in that window, i.e. two failed runs in a
  row, held for 5 minutes (about 25-30 minutes after the first failure). One bad run does not page. Look at the failing checks:
  `journalctl -u domainscope-search-probe.service -n 80` on CT108 (the `[FAIL]` lines name the query, the HTTP code, the rows and the
  `no_results_reason`); reproduce from a DomainScope checkout with `scripts/search-probe.sh --all --markets 20`. A probe that could not run
  says so in the same journal ("the probe exited N without valid metrics", "ran past 720s").
- **`DomainScopeSearchProbeStale`**: no run has finished for 3 hours, or the series has been absent for 6 hours (or never existed). CT108 is
  stopped about an hour each night by its backup (`ct108-nightly`, 01:30Z; the node exporter is gone meanwhile): `last_over_time` keeps the last
  timestamp through that window, so it counts as age, not as a vanished series. Check `systemctl status domainscope-search-probe.timer
  domainscope-search-probe.service` on CT108, or `scripts/domainscope-search-probe-install.sh --status` from this repository.

Both are tested with promtool (`tests/promtool/domainscope_search_rules_test.yml`: two failed runs alert, one does not, alternating failures do
not, a failure followed by the nightly stop does not, the 70-minute stop raises nothing, a stopped timer is stale after 3 hours, a builder that
stays down stays stale).

## Install, update, remove

```sh
# after the change is merged, from a checkout at origin/main (refuses files that differ from origin/main)
scripts/domainscope-search-probe-install.sh            # wrapper to /usr/local/bin, units to /etc/systemd/system (replaced files kept as .bak-<UTC>)
scripts/domainscope-search-probe-install.sh --enable   # also enable the timer and run the probe once
scripts/domainscope-search-probe-install.sh --status   # timer, last result, journal tail, metrics
```

Rules: install `config/prometheus/rules/domainscope-search.yml` on the monitoring VM as `/etc/prometheus/rules/domainscope-search.yml`
(`root:prometheus 0640`, `promtool check rules`, then `sudo systemctl kill -s HUP 0mcp-prometheus`); the monitoring_vm role ships it too
(`monitoring_prometheus_adopted_rule_files`). Deploy the rules only after the first run wrote its metrics: before that, `absent_over_time`
makes `DomainScopeSearchProbeStale` fire after 10 minutes.

Stop it: `systemctl disable --now domainscope-search-probe.timer` on CT108 (then the stale alert fires after 3 hours: silence it or remove the
rule file). Remove it: disable the timer, delete the two units, the wrapper, `/var/lib/domainscope-search-probe` and the `.prom` file.

## Changing what is checked

The golden queries, their minimum row counts and the market-cell sampling live in the DomainScope repository (`scripts/search-golden-queries.tsv`,
`scripts/search-probe.sh`), not here: a merged change there is used by the next run. A query that fails for a known reason with an open fix
gets the gate `known-failing` there (it is still run and reported) instead of being removed, so the alert stays about regressions.

The wrapper checks that main's probe has `--metrics-file` before it runs it (a probe that cannot write metrics is recorded as a failed run,
"has no --metrics-file" in the journal). It reads the whole script first and matches after: until 2026-10-22 it piped `git show` into
`grep -q` under `pipefail`, grep stopped at the first match, git died of SIGPIPE, and about 4 runs in 10 were recorded as failed with "has no
--metrics-file" although the flag was there (false failures 21:19Z and 21:49Z on 2026-10-21; never two in a row, so the alert did not fire).
`tests/test_domainscope_search_probe.py` runs the check against a copy of the real probe (`tests/fixtures/domainscope-search-probe/search-probe.sh`,
go-url-categorizer-api main 5cd0f55c0) and against a 2 MB probe whose flag is on line 2, where the old check failed every time.
