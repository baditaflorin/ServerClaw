# SLO Tracking

## Purpose

Operate the ADR 0096 service-level objective stack from the repository source of truth.

## Source Of Truth

- [`config/slo-catalog.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/slo-catalog.json)
- [`scripts/generate_slo_rules.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/generate_slo_rules.py)
- [`config/prometheus/rules/slo_rules.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/prometheus/rules/slo_rules.yml)
- [`config/prometheus/rules/slo_alerts.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/prometheus/rules/slo_alerts.yml)
- [`config/prometheus/file_sd/slo_targets.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/prometheus/file_sd/slo_targets.yml)
- [`config/grafana/dashboards/slo-overview.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/grafana/dashboards/slo-overview.json)

## Verified Endpoints (Probe Overlay)

`config/slo-catalog.json` is the design-intent catalog assembled from the service bundles. Its URLs use placeholder
domains and some point at retired addresses, so it is not probed as-is. `config/slo-probe-overlay.json` is the
deployment overlay: it lists, per catalog SLO, either a **verified endpoint** (real URL, optional objective override,
probe path `edge` or `direct`, optional `tls`) or an **excluded** entry with the reason. Every catalog SLO must be in
exactly one of the two lists (enforced by `tests/test_generate_slo_rules.py`). Only verified endpoints are rendered
into `slo_rules.yml`, `slo_alerts.yml`, `slo_targets.yml` and `https_tls_*`.

- `via: edge` endpoints use `https://<name>.{{ platform_domain }}/<path>`. The monitoring VM cannot reach the public
  address, so the targets file connects to `{{ monitoring_slo_edge_connect_host }}` (the nginx edge private address) and
  the `slo-blackbox` relabel rules pass the public name as Host/SNI (`probe_hostname`) and as `instance`
  (`display_url`). Both placeholders are rendered by the monitoring role when the target files are templated.
- `via: direct` endpoints are private `http://10.10.10.x:port/path` URLs that answer from the monitoring VM.
- `tls: true` adds the endpoint to the HTTPS/TLS assurance job: warn below 21 days, critical below 7 days.

Alert policy (all generated, names unchanged): `SLOFastBurn_*` (14x, 5m and 1h windows) is the only critical alert;
`SLOSlowBurn_*` and `SLOBudgetCritical_*` are warnings. Each alert is guarded by a minimum amount of probe history
(30 minutes for fast burn, 6 hours for slow burn, 24 hours for budget) so a freshly added target cannot fire from a
handful of samples, and the success-ratio recording rules drop series that are no longer scraped so a retired target
cannot keep alerting from its old 30-day average.

### Adding or re-enabling an endpoint

1. Probe it from the monitoring VM through blackbox exporter and require a 2xx:
   `curl -s 'http://127.0.0.1:9115/probe?target=https://<edge-ip>/<path>&module=http_2xx_follow_redirects&hostname=<name>'`
   (omit `hostname` for direct endpoints).
2. Move its entry from `excluded` to `endpoints` in `config/slo-probe-overlay.json` (a new SLO first goes into its
   service bundle and the generated catalog).
3. `python scripts/generate_slo_rules.py --write && python scripts/generate_https_tls_assurance.py --write`
4. `promtool test rules tests/promtool/slo_rules_test.yml` (and `python -m pytest tests/test_slo_promtool_rules.py`).

Endpoints under `excluded` are deliberately not paged: down at the edge (HTTP 502), behind SSO with no
unauthenticated health path, or not reachable from the monitoring VM. Decide per service whether it should be paged
before moving it back.

## Regenerate Assets

Run:

```bash
make generate-slo-rules
```

This rewrites the committed Prometheus rules, blackbox targets, and Grafana dashboard from the catalog.
The generated Prometheus files include `# BEGIN SERVICE: <id>` and
`# END SERVICE: <id>` markers so `scripts/decommission_service.py` can remove a
service's SLO blocks without line-level YAML edits.

## Validate Before Merge

Run:

```bash
uv run --with pyyaml python scripts/generate_slo_rules.py --check
uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate
uv run --with pytest --with fastapi --with qdrant-client --with pyyaml --with jsonschema python -m pytest tests/test_slo_tracking.py tests/test_platform_context_service.py tests/test_ops_portal.py tests/test_promotion_pipeline.py
make syntax-check-monitoring
```

## Live Convergence Expectations

After a deliberate apply from `main`, the monitoring role should:

- install and bind `prometheus-blackbox-exporter` on `127.0.0.1:9115`
- copy the generated SLO rule files into `/etc/prometheus/rules/`
- copy the generated probe targets into `/etc/prometheus/file_sd/`
- import the `LV3 SLO Overview` dashboard into Grafana

## Inspect Current SLO State

From a context-service deployment that can reach Prometheus:

```bash
curl -s -H "Authorization: Bearer $PLATFORM_CONTEXT_API_TOKEN" http://127.0.0.1:8010/v1/platform/slos
```

For local catalog inspection without live metrics:

```bash
python scripts/slo_tracking.py --status
```

## Promotion Gate Behaviour

`scripts/promotion_pipeline.py` rejects promotion when:

- the SLO query path cannot be evaluated
- required SLO samples are missing
- any tracked SLO reports less than 10% error budget remaining

If promotion is unexpectedly rejected, inspect the `slo_gate` section in the returned gate payload first.

## Updating Objectives

1. Edit [`config/slo-catalog.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/slo-catalog.json).
2. Regenerate assets with `make generate-slo-rules`.
3. Re-run the validation commands above.
4. Update ADR metadata if the implementation state changed.

Do not edit `config/prometheus/rules/slo_rules.yml`,
`config/prometheus/rules/slo_alerts.yml`, or
`config/prometheus/file_sd/slo_targets.yml` by hand; changes should flow from
`config/slo-catalog.json` and preserve the service block markers.
