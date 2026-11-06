# WS-0535: Alert rules for the agent-history store (git only)

## Status

In progress. The pull request is open and not merged; nothing was applied, no `[live-apply]` marker, no receipt, no version bump.

## Goal

ADR 0494 (added by the guest pull request, ws-0534) puts the agent-history store on its own guest, VM 155. Its metrics reach the 0mcp Prometheus through the node exporter textfile collector. This workstream is the alerting for it.

## Change

- `config/prometheus/rules/agent-history.yml`: 16 alerts in three groups. Store: `AgentHistoryStoreDown`, `AgentHistoryMetricsStale`, `AgentHistoryIngestLagHigh` (p95 of the ingest-lag histogram), `AgentHistorySpoolDepthHigh` (per host), `AgentHistoryCollectorSilent` (48 hours: laptops sleep), `AgentHistoryRedactionHit`, `AgentHistoryQuerySlow` (p95 of the query histogram), `AgentHistoryParseErrors`, `AgentHistoryRejectedLines`, `AgentHistoryClockSkew`. Canary: `AgentHistoryCanaryLeak`, `AgentHistoryCanaryStale`, `AgentHistoryCanaryMissing`. Storage: `AgentHistoryDataDiskLow`, `AgentHistoryDataDiskFillingFast`, `AgentHistoryBackupMissing`.
- `tests/promtool/agent_history_rules_test.yml`: 24 cases, each alert firing and not firing, with the fully rendered annotations.
- `tests/test_agent_history_rules.py`: pins severities and delays, the metric names, the histogram reads, the mount point and the open severity question; runs `promtool check` and the unit tests when promtool is installed.
- `monitoring_vm/defaults/main.yml` and `tests/test_adopted_prometheus_rules.py`: the file is added to the adopted list, so a later converge of the monitoring role ships it (root:prometheus 0640, SIGHUP) like the other rule files.

## Severity (question 16 is answered: warning only)

The owner decided on 2026-10-29 that nothing pages: warning only, including for a canary leak. So `AgentHistoryCanaryLeak` is `warning` (an earlier revision of this change had proposed `critical`), `AgentHistoryRedactionHit` is `warning`, and no alert is `critical`. The staleness alert `AgentHistoryCanaryStale` stays a `warning`. In this repository's Alertmanager, `warning` goes to the ntfy warning topic and `info` is dropped, so the four `info` alerts are visible in Prometheus only. The pytest pin asserts that no alert is critical.

## Deliberately not here

- Backup age: the generic `PbsBackupGroupStale` (26 hours) and `PbsBackupGroupStaleCritical` (50 hours) already cover `vm/155` once it has a first snapshot. `AgentHistoryBackupMissing` covers the gap they cannot: a group that never got a snapshot.
- An audit-gap alert: it needs the read token, which the metrics bridge does not hold (it holds the metrics-only token).
- A blackbox SLO probe: the monitoring guest has no route to the loopback listener, by design.

## What merging does and does not do

Does: put the rule file, its tests and the adopted-list line on `main`. Does not: copy the file to the monitoring VM, reload Prometheus, or change any host. The guest does not exist yet, so the alerts would be silent until its bridge writes `agent_history.prom` even after a converge; `AgentHistoryCanaryMissing` and `AgentHistoryBackupMissing` only count once the store is scraped.

## Verification

`promtool check rules` (16 rules), `promtool test rules` (24 cases, all SUCCESS), `tests/test_agent_history_rules.py` and `tests/test_adopted_prometheus_rules.py` (47 tests), and the repository pre-push gate on the build server.

Not verified: that the 0mcp Prometheus discovers the guest's node exporter, that a scraped textfile keeps the store's own `host` label (a scrape-config label of the same name would rename it to `exported_host` and the annotations would print an empty host; the alerts would still fire), the real `agent_history_spool_depth` range under load (20 batches is a first guess to tune after the pilot), and the rules against live data (there is none).
