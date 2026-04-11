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

## Regenerate Assets

Run:

```bash
make generate-slo-rules
```

This rewrites the committed Prometheus rules, blackbox targets, and Grafana dashboard from the catalog.

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
