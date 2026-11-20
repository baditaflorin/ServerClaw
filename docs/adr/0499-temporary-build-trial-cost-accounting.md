# ADR 0499: Durable Cost Accounting for Temporary Build Workers

- Status: Accepted
- Implementation Status: Implemented and verified in production
- Implemented In Repo Version: 0.179.66
- Implemented In Platform Version: 0.179.66
- Implemented On: 2026-11-19
- Date: 2026-11-19
- Concern: monitoring, ci-cd, lifecycle
- Tags: build-worker, woodpecker, grafana, cost, trial, lifecycle
- Related: ADR 0496, ADR 0497

## Context

A short-lived build worker needs a useful end-of-trial cost conclusion. A
dashboard based only on Prometheus's rolling samples can lose the start of a
trial when its duration exceeds sample retention. Woodpecker pipeline records
also need stable execution-host attribution across worker registration
rotation. A pipeline may be split across multiple workers, and one pipeline may
contain multiple workflow executions, so the accounting unit must be explicit.

Standalone Buildx and Fleet Runner operations are separate from Woodpecker
pipeline records. A CI dashboard must not imply that its pipeline count equals
the number of image artifacts or all work performed by a host.

## Decision

1. Store each trial's control plane, execution host, historical and current
   worker registration IDs, UTC interval, and owner-provided spend in the
   private Fleet State `ci-build-trials.json` file. Do not put host-specific
   billing values in this generic repository.
2. Identify a worker consistently with an explicit `builder=<execution-host>`
   Woodpecker agent label. Preserve historical registration IDs in the private
   trial definition so earlier workflows remain attributable after agent
   rotation or deletion.
3. Backfill pipeline details from trial start and persist a deduplicated ledger
   keyed by Woodpecker repository ID and pipeline number in the metrics
   exporter's existing durable state. Update open and recent pipeline outcomes
   on later collections. Export aggregate gauges from that ledger so dashboard
   totals remain queryable past Prometheus sample retention.
4. Count one unique pipeline when it was created inside the configured trial
   interval and at least one of its workflows ran on the selected worker. Count
   a mixed-host pipeline once. Count each assigned workflow separately.
5. Show recorded spend, unique completed and successful pipelines, pipeline
   outcomes, per-repository and per-day usage, workflow executions, cost per
   completed pipeline, cost per successful pipeline, and cost per worker
   workflow. Expose a historical-coverage gauge and keep cost ratios gated until
   the exporter has completed its backfill without unresolved API failures.
6. State in the dashboard that these ratios cover Woodpecker CI only. They do
   not count image artifacts, standalone Buildx invocations, Fleet Runner jobs,
   or workflows that ran only on other hosts.
7. Provision the dashboard through the monitoring VM role, using the configured
   Prometheus datasource UID and deployment-prefixed dashboard UID.

## Implementation and verification

The private Fleet State trial record and durable exporter ledger are live. The
exporter changes are merged in `baditaflorin/fleet-woodpecker-metrics` PRs #1,
#2, and #3, and CT108 now reports complete historical coverage. The first
install exposed a state-variable shadowing bug; the installer rolled back, the
fix was merged, and the collector was reinstalled. A terminal pipeline that
never created a workflow also exposed an API response shape that the exporter
initially treated as unreadable; the collector now records that as zero worker
usage while leaving active records incomplete.

The managed dashboard and narrow `build_trial_dashboard` tag were merged in
PFS PR #709. The first live apply copied and rendered the dashboard file but
stopped at its Grafana API lookup: the tag did not include the existing Grafana
admin password read and fact tasks. PFS PR #713 adds those prerequisites to the
tag and a regression check. The scoped apply from merged main completed on
2026-11-19; the Grafana API returned dashboard UID `0mcp-build-trial-cost`,
and Prometheus reported complete collection (`1`). A verified local SSH
forward reaches Grafana; the public route still refuses connections. The live
apply receipt is `ws-20261119-kamateratmp-trial-cost-accounting-apply-receipt`.

The live spend amount, interval, and interim usage figures remain in private
trial configuration and Grafana state; this generic repository records no
host-specific billing values. The configured interval is 30 days. Confirm the
provider's billing cutoff and actual invoice before drawing the final cost
conclusion.

## Consequences

- Trial totals remain available after the Prometheus retention window, provided
  the exporter state file remains durable and its collection reports complete.
- Cost per pipeline and cost per worker workflow answer different questions;
  neither is a count of produced artifacts.
- A new trial requires only a private trial record and a stable worker label;
  the same dashboard can display multiple trials.
- The final cost conclusion must disclose incomplete historical coverage or
  missing evidence rather than treating a partial count as the full denominator.
