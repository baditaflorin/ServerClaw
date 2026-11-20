# Kamateratmp trial cost accounting

## Goal

Make the 30-day Kamateratmp trial measurable in Grafana, including completed
Woodpecker pipelines, outcomes, workflow executions, and cost per completed
pipeline against the spend recorded in private trial configuration.

## Confirmed data and discrepancies

- Kamateratmp’s Woodpecker agent has a `site=kamateratmp` label, but the
  metrics exporter uses `builder=<worker-id>` for stable worker attribution.
- The exporter’s existing pipeline metrics cover a rolling 24 hours; local
  Prometheus retention is 15 days. A 30-day dashboard based on those samples
  would undercount the trial.
- `docs/runbooks/monitoring-stack.md` and older Grafana instructions use
  `10.10.10.40` and the `100.64.0.1` jump host. Current inventory puts the
  monitoring VM at `10.10.10.40`; the old subnet-router peer is offline. The
  current SSH alias reaches Grafana locally, Grafana health returns 200, and
  the active Prometheus datasource UID is `0mcp-prometheus`. The public
  Grafana endpoint still refuses connections.
- The cost view must label its scope as Woodpecker pipelines and workflow
  executions. Standalone Buildx operations are not included unless they produce
  their own durable event metric.
- The exporter installer expects the private trial file at
  `/root/fleet-state/ci-build-trials.json` on CT108, but that host does not have
  a Fleet State checkout. The canonical file was staged there with root-only
  permissions from the private Fleet State repository; installer and drift
  checks now agree with that location.
- The first exporter install rolled back because a queue loop shadowed the
  persistent state mapping. After that fix, one terminal `error` pipeline that
  had no workflow records kept the historical-coverage metric false. The
  collector now treats an omitted `workflows` field as an empty list only for
  terminal pipelines; active pipelines remain incomplete until readable.

## Work plan

1. Add a private, canonical trial accounting record in Fleet State with the
   worker, control plane, start/end timestamps, and USD cost.
2. Extend `fleet-woodpecker-metrics` to backfill once from trial start, persist
   pipeline identities in its existing state file, and export durable trial
   aggregates that remain available after Prometheus sample retention expires.
3. Add `builder=kamateratmp` to the worker’s canonical Woodpecker labels.
4. Add and provision a Grafana dashboard with pipeline counts/outcomes,
   workflow execution counts, USD spend, cost per worker workflow, and cost
   per completed or successful pipeline. Gate cost ratios on complete
   historical collection and disclose that these are CI measures, not image
   artifact counts.
5. Fix stale monitoring endpoint instructions and publish a live-apply receipt
   only after Grafana and the metric collector are reachable and verified.

## Status

The exporter ledger is merged and live on CT108. Its timer is active, its
existing state file contains the durable trial ledger, and historical coverage
reports complete. The spend input and exact interval remain in private Fleet
State. The three exporter PRs passed `ci/woodpecker/pr/woodpecker`, and CT108
matches the merged exporter repository.

PFS PR #709 merged the dashboard and scoped Ansible tag. The first live apply
copied and rendered the dashboard but exposed a missing tag dependency for the
Grafana credential-read tasks. PFS PR #713 fixed that dependency, added a
regression check, and corrected the scoped runbook invocation. The retry from
merged main completed on 2026-11-19 using the private 0mcp connection overlay.
The receipt records the successful import on monitoring VM 140. Grafana's API
returned HTTP 200 for UID `0mcp-build-trial-cost`; the Prometheus trial coverage
metric was `1`.

At the 2026-11-19 22:03 UTC snapshot, Prometheus reported complete historical
coverage (`1`). The accounting scope is Woodpecker pipelines created inside the
configured trial interval with at least one workflow on the selected worker;
mixed-host pipelines count once. Standalone Buildx and Fleet Runner jobs are
excluded. Host-specific cost, interval, and usage figures remain in private
Fleet State and Grafana rather than this generic repository.

The configured interval is 30 days. The provider's billing cutoff is not
confirmed, so reconcile the private cost input with the provider invoice before
drawing the final conclusion. The public Grafana route still refuses
connections. A local SSH tunnel on port 13000 reaches the dashboard at the
deployment-prefixed `build-trial-cost` UID.

## Next

Keep the exporter and dashboard collecting through the configured interval.
At sunset, confirm the provider invoice and billing cutoff, verify historical
coverage remains `1`, record the final pipeline/workflow totals and cost ratios,
and document exclusions and failed outcomes. The repo's release manager
currently reports unrelated release blockers, so this live-state record is
being landed without forcing a version cut. The workstream requests a minor
release because it adds a new operator-visible dashboard capability.
