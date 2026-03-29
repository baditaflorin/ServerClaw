# ADR 0305: k6 For Continuous Load Testing And SLO Error Budget Burn Validation

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

`config/slo-catalog.json` defines availability SLOs for every published platform
service (99.0% to 99.9% per 30-day window). Uptime Kuma (ADR 0027/0123) probes
each service with single HTTP requests at regular intervals to measure
availability. This is sufficient for detecting a complete outage, but it does not
answer a set of operationally important questions:

- does the service meet its SLO **under representative concurrent load**? A
  service that responds in 200ms to a single probe may return 5xx errors when
  five operators use it simultaneously
- what is the error budget burn rate when the platform is under normal
  operational load? The SLO window calculation requires actual request volume,
  not just polling pings
- will a newly proposed version bump (via Renovate, ADR 0297) introduce a
  latency regression under load before it reaches production?

`config/synthetic-transaction-catalog.json` already defines representative
operator-facing HTTP transaction scenarios for restore rehearsal. Those same
scenarios are directly usable as load test scripts.

k6 (`grafana/k6`) is a Go-based load testing tool maintained by Grafana Labs.
It is AGPL-3.0-licensed, ships as a single Go binary and a Docker image, and has
been in production use since 2017. Test scripts are written in JavaScript. k6
natively outputs metrics in Prometheus remote-write format, integrates directly
with Grafana for live dashboards, and produces a structured JSON result summary
suitable for CI assertion. It is API-ready: `k6 run --out json=results.json`
produces a machine-readable result that can be parsed by any tool without
a separate export step.

## Decision

We will integrate **k6** as the platform's load testing and SLO budget burn
validation tool, running both in pre-release CI gates and as scheduled Windmill
jobs.

### Deployment rules

- k6 runs as a Docker Compose `run` step in Gitea Actions on `docker-build-lv3`
  and as a Windmill job for scheduled platform-health load probes
- the k6 Docker image is pulled through Harbor (ADR 0068) and pinned to a SHA
  digest; the version is tracked in `versions/stack.yaml`
- load tests run against the staging environment (ADR 0183) or the live platform
  in a rate-limited mode; they never run against production at full throughput
  without an explicit maintenance-window declaration (ADR 0080)
- k6 scripts are stored under `config/k6/scripts/` and are version-controlled;
  script changes require PR review

### Test scenario model

Three k6 test scenario types are defined:

1. **Smoke test** (`config/k6/scripts/smoke/`): 1–3 virtual users, 60-second
   duration, checks that every endpoint in `slo-catalog.json` responds with the
   expected HTTP status; runs as a blocking CI gate step before any release merge
2. **Load test** (`config/k6/scripts/load/`): virtual users ramped to the
   declared `typical_concurrency` value in `config/capacity-model.json` for
   5 minutes; asserts p95 response time stays below the SLO latency threshold
   defined per service in `slo-catalog.json`; runs weekly via Windmill
3. **Soak test** (`config/k6/scripts/soak/`): load-level users held for 30
   minutes; validates memory stability, no connection pool exhaustion, and no
   error rate creep; runs monthly via Windmill as a scheduled job

### Output and receipt model

- k6 emits a structured JSON summary at `receipts/k6/<scenario>-<service>-<date>.json`
  after every run; this follows the same receipt convention as other platform
  artefacts
- k6 metrics are pushed to Prometheus via remote-write during every run; the
  existing Grafana dashboards on `monitoring-lv3` gain a `k6_*` metric namespace
  showing request rate, error rate, and p95 latency over the test window
- the CI gate step reads the JSON summary and fails if: error rate > 1% during
  the smoke test, or p95 latency exceeds the service's SLO threshold
- a Windmill post-run job compares the weekly load test result against the
  previous baseline and publishes a NATS `platform.slo.k6_regression` event
  (ADR 0276) if p95 latency has regressed by more than 20%

### SLO error budget integration

- the weekly k6 load test result informs the `error_budget_consumed_pct` field in
  the SLO catalog receipt; this is a computed estimate based on observed error
  rates under load, complementing the availability-based Uptime Kuma signal
- services with an error budget below 20% remaining trigger an ntfy
  `platform.slo.warn` notification (ADR 0299) and block Renovate version bump
  PRs for that service (via a Gitea Actions check that reads the latest k6 receipt)

## Consequences

**Positive**

- latency regressions in a new version are detected by the smoke test before the
  release merges; operators are informed before users see degraded performance
- the weekly load test provides an empirical SLO budget burn rate that is more
  accurate than a binary availability probe under traffic
- k6's Prometheus remote-write output means load test results appear in the same
  Grafana workspace as all other platform metrics with no additional
  instrumentation

**Negative / Trade-offs**

- load tests consume real resources on the staging or production environment; test
  schedules must be coordinated with maintenance windows to avoid interfering with
  legitimate operator traffic
- k6 JavaScript scripts require operator skill to write and maintain; poorly
  written scripts (missing sleep between iterations, unrealistic request
  patterns) produce misleading results
- the Prometheus remote-write endpoint must be reachable from the build host or
  the Windmill worker; this requires a network path from `docker-build-lv3` to
  `monitoring-lv3` that is currently unused

## Boundaries

- k6 tests cover HTTP endpoints declared in `slo-catalog.json`; it does not
  test TCP, gRPC, or WebSocket endpoints in the first phase
- k6 does not replace synthetic transactions (ADR `synthetic-transaction-catalog.json`);
  synthetic transactions validate correctness of individual journeys while k6
  validates throughput and latency under load
- k6 is not a chaos engineering tool; it generates normal load, not failure
  conditions; Falco and the fault injection framework (ADR 0171) cover failure
  simulation

## Related ADRs

- ADR 0027: Uptime Kuma for service availability monitoring
- ADR 0080: Maintenance window and change suppression protocol
- ADR 0097: Alerting routing and oncall runbook model
- ADR 0119: Budgeted workflow scheduler
- ADR 0123: Service uptime contracts and monitor-backed health
- ADR 0183: Staging environment
- ADR 0192: Capacity classes for production and staging guests
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0292: Apache Superset as the SQL-first BI layer
- ADR 0297: Renovate Bot as the automated stack version upgrade proposer
- ADR 0299: Ntfy as the push notification channel

## References

- <https://github.com/grafana/k6>
