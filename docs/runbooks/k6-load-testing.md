# k6 Load Testing

## Purpose

Run the repo-managed ADR 0305 k6 smoke, load, and soak probes against the
declared latency-SLO services, store the resulting receipts under
`receipts/k6/`, and surface regression or remaining-budget warnings through the
private platform event and notification paths.

## Repo Entry Points

- `make k6-smoke`
- `make k6-load`
- `make k6-soak`
- `python3 scripts/k6_load_testing.py --validate`

The Windmill worker seeds `f/lv3/k6_load_testing` and schedules:

- `f/lv3/k6_load_weekly`
- `f/lv3/k6_soak_monthly`

## Inputs

- `config/slo-catalog.json`
  Defines the target URLs and latency thresholds.
- `config/capacity-model.json`
  Defines `service_load_profiles` for the services that participate in load and
  soak probes.
- `config/image-catalog.json`
  Pins the `k6_runtime` image digest.
- `versions/stack.yaml`
  Supplies the private Prometheus URL used to derive the remote-write endpoint.

## Outputs

- Receipts: `receipts/k6/<scenario>-<service>-<timestamp>.json`
- Raw summary exports: `receipts/k6/raw/<timestamp>-<scenario>-summary.json`
- Optional NATS regression event: `platform.slo.k6_regression`
- Optional ntfy warning topic: `platform-slo-warn`

## Live-Apply Notes

- Prometheus remote-write must be reachable on the private monitoring address
  from `docker-build` and `docker-runtime`.
- On `monitoring`, Prometheus must listen on the guest-reachable private
  interface (`0.0.0.0:9090` for the current unit) rather than `127.0.0.1:9090`
  or the build-host smoke/load path will time out even when the local service
  is healthy.
- Private OpenFGA smoke and load probes must target the guest-reachable runtime
  listener on `http://10.10.10.20:8098/healthz`; the
  `http://100.64.0.1:8014` controller proxy is Tailscale-bound and is only for
  controller-local bootstrap and verification.
- If the public Keycloak smoke probe fails, check
  `https://sso.example.com/realms/lv3/.well-known/openid-configuration` directly
  before treating the result as a repo regression. The 2026-03-31 latest-main
  replay returned `502 Bad Gateway` from that exact URL, which confirmed a live
  edge/runtime failure rather than a k6-runner contract break.
- If the public Keycloak OIDC probe and the guest-local
  `http://10.10.10.20:8091/health/ready` check both time out or fail, preserve
  the k6 receipts and outage evidence as live-service degradation; do not
  rewrite the run into a repository-only failure.
- During `docker-runtime` redeploys, OpenFGA health can flap briefly while
  the container restarts; if the first k6 smoke run hits connection refusals,
  re-check `http://10.10.10.20:8098/healthz` from the build host before
  concluding the repo change regressed the service.
- The private Gitea `validate.yml` smoke gate runs inside a containerized runner,
  so it must export `LV3_DOCKER_WORKSPACE_PATH` before calling `make k6-smoke`
  or the nested `docker run` cannot mount the checkout from the runner host.
- The public GitHub mirror validation stays repo-only for ADR 0305 because the
  hosted runner cannot reach the private Prometheus remote-write path or the
  private OpenFGA health endpoint.
- Smoke probes are intended to remain the blocking CI path. Load and soak probes
  are scheduled Windmill diagnostics and should be paused or coordinated with a
  maintenance window if a service is already degraded.
- If a load or soak receipt shows `error_budget_remaining_pct < 20`, treat it as
  a service-health warning and review the latest receipt before approving a
  version promotion for that service.
- Keep the k6 ntfy warning topic hyphenated. The live ntfy runtime rejects
  dotted topic patterns, so the repo-managed warning slug is
  `platform-slo-warn` even though related platform event subjects remain
  dotted.
- Controller-side exact-main `make k6-load` and `make k6-soak` runs now fail
  fast if the configured NATS regression-publication endpoint is unreachable and
  preserve the receipts with a warning instead of hanging in the post-run
  notification path; set `LV3_NATS_URL` explicitly when running from a machine
  that needs a different NATS route than the repo-managed service catalog.
- For controller-local validation runs, expect warning-only notification
  evidence unless the machine running `make k6-load` also has working access to
  the intended NATS and ntfy endpoints; those warnings should not hide or
  rewrite the actual k6 smoke/load result.

## Verification

1. Run `make k6-smoke K6_ARGS="--service keycloak --service openfga"`.
2. Run `make k6-load K6_ARGS="--service keycloak --service openfga"`.
3. Confirm new receipts exist under `receipts/k6/` and `receipts/k6/raw/`.
4. Run `python3 scripts/k6_load_testing.py --validate`.
5. Query Prometheus for the latest `k6_*` samples during the run window if the
   remote-write path was enabled live.
