# ADR 0305: k6 For Continuous Load Testing And SLO Error Budget Burn Validation

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.120
- Implemented In Platform Version: 0.130.75
- Implemented On: 2026-03-31
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

### Implemented live replay

- the branch-local live apply on 2026-03-31 replayed the monitoring, guest
  network policy, Windmill, and OpenFGA surfaces needed for the ADR 0305
  execution path, with the successful corrective runs preserved under
  `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-monitoring-r7.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-openfga-r5.txt`,
  and `receipts/live-applies/evidence/2026-03-31-ws-0305-converge-windmill-r4.txt`
- the authoritative build-server smoke replay passed from
  `docker-build-lv3`, producing synced receipts
  `receipts/k6/smoke-keycloak-20260331T103411Z.json` and
  `receipts/k6/smoke-openfga-20260331T103411Z.json` plus the raw summary
  export, as captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-smoke-r9.txt` and
  `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-receipt-sync-r2.txt`
- the authoritative build-server load replay now preserves failed receipts and
  returns a non-zero exit when thresholds are crossed instead of dropping the
  evidence path; the final run is captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-load-r6.txt` and
  `receipts/live-applies/evidence/2026-03-31-ws-0305-k6-receipt-sync-r3.txt`
- the live platform did not meet the configured 1% error-rate objective during
  that final load replay: Keycloak recorded `1725` requests with `400` failures
  (`23.19%` error rate) and OpenFGA recorded `995` requests with `42` failures
  (`4.22%` error rate), both with error budget remaining reduced to `0.0%` in
  the synced receipts
- the first exact-main closeout rebased the workstream onto latest realistic
  `origin/main` commit `5c7e07235f7b0da1f756148e145397f0ac6ceb10` and used
  committed source `0d6e8c9eb5d9d086e74cf92d8165248295baa076` for the initial
  canonical replay, as recorded in
  `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-candidate-source-commit-r3-0.177.118.txt`
- the first exact-main smoke attempt exposed live drift rather than a repo
  regression: `monitoring-lv3` still had Prometheus bound to `127.0.0.1:9090`
  and `docker-runtime-lv3` was concurrently churning the OpenFGA container;
  the repair path is preserved under
  `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-smoke-r5-0.177.118.txt`,
  `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-converge-monitoring-r8-0.177.118.txt`,
  and
  `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-prometheus-bind-manual-r1-0.177.118.txt`
- after that correction loop, the exact-main smoke replay passed from
  committed source and produced
  `receipts/k6/smoke-keycloak-20260331T133226Z.json` plus
  `receipts/k6/smoke-openfga-20260331T133226Z.json`; Keycloak recorded `110`
  requests with `0` failures and OpenFGA recorded `112` requests with `0`
  failures, as captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-smoke-r6-0.177.118.txt`
- the exact-main load replay completed from committed source without the
  earlier NATS deadlock and preserved the truthful load outcome in
  `receipts/k6/load-keycloak-20260331T133416Z.json`,
  `receipts/k6/load-openfga-20260331T133416Z.json`, and
  `receipts/k6/raw/20260331T133416Z-load-summary.json`, as captured in
  `receipts/live-applies/evidence/2026-03-31-ws-0305-mainline-k6-load-r3-0.177.118.txt`;
  Keycloak recorded `1585` requests with `441` failures (`27.82%` error rate)
  and failed the 1% objective, while OpenFGA recorded `1184` requests with `8`
  failures (`0.68%`) and passed the run even though its warning path still
  reported `error_budget_remaining_pct: 0.0`
- repository automation gaps discovered during live apply were fixed in-repo on
  this workstream: gitless snapshot commit capture, relative repo-root handling,
  k6 summary parsing, failure-path receipt generation, non-fatal ntfy warning
  handling, remote build workspace retention cleanup, and bounded exact-main
  notification publication when controller-local NATS or ntfy are unavailable,
  plus synced remote gate status handoff and unresolved-only local fallback
  reruns when the build host loses runner availability after partial success,
  together with a widened shared `packer-validate` timeout budget so the
  controller-local arm64 fallback can finish the emulated x86 runner image
- `origin/main` then advanced again to commit
  `2411a7cd428e0eba17168aa5eed66f04c4ed48dd`, carrying repository version
  `0.177.118` and platform version `0.130.77`, so the exact-main closeout was
  first recut on that newer baseline
- `origin/main` later advanced again to commit
  `97f05802253cbb8fb4640249fdb8485fd7ecdde6`, which still carried repository
  version `0.177.119` and platform version `0.130.77` after ADR 0306 landed,
  so the final merge-to-main closeout for ADR 0305 was recut as repository
  release `0.177.120` while preserving the latest realistic `0.177.119` k6
  evidence
- the latest-main smoke replay from committed source
  `6d476f01e75a2ecf31d8ce13df1250bc6aec193e` preserved current live Keycloak
  degradation instead of masking it: direct probing of
  `https://sso.lv3.org/realms/lv3/.well-known/openid-configuration` returned
  `502 Bad Gateway`, the synced smoke receipt
  `receipts/k6/smoke-keycloak-20260331T145155Z.json` recorded `110` requests
  with `110` failures, and `receipts/k6/smoke-openfga-20260331T145155Z.json`
  still passed with `112` requests and `0` failures
- the latest-main load replay from the same committed source also preserved the
  truthful degraded platform outcome under the latest realistic `0.177.119`
  baseline: Keycloak
  recorded `1600` requests with `1184` failures (`74.00%` error rate) in
  `receipts/k6/load-keycloak-20260331T145555Z.json`, OpenFGA recorded `1182`
  requests with `14` failures (`1.18%`) in
  `receipts/k6/load-openfga-20260331T145555Z.json`, Prometheus remote-write
  repeatedly timed out, and the warning-only ntfy publication path returned
  `404 Not Found` without hanging the run
- the canonical exact-main closeout receipt is
  `receipts/live-applies/2026-03-31-adr-0305-k6-mainline-live-apply.json`,
  published in repository release `0.177.120` while keeping the first verified
  platform implementation version at `0.130.75`

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
- the implemented live replay proved the dependent telemetry path is itself an
  operational risk surface: during the 2026-03-31 exact-main closeout,
  Prometheus remote-write calls from the k6 runner to `monitoring-lv3`
  repeatedly timed out until Prometheus was rebound to the guest-reachable
  address, and the later latest-main `0.177.119` rerun still preserved public
  Keycloak `502 Bad Gateway`, OpenFGA threshold breach, and warning-only
  notification failures without hiding the underlying smoke/load result

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
