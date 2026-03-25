# Workstream ADR 0096: SLO Definitions and Error Budget Tracking

- ADR: [ADR 0096](../adr/0096-slo-definitions-and-error-budget-tracking.md)
- Title: Machine-readable SLO catalog with generated Prometheus rules, blackbox probe targets, Grafana dashboard, and promotion-gate enforcement
- Status: live_applied
- Branch: `codex/live-apply-0096`
- Worktree: `.worktrees/adr-0096`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0064-health-probes`, `adr-0073-promotion-gate`, `adr-0092-platform-api-gateway`
- Conflicts With: none
- Shared Surfaces: `config/slo-catalog.json`, `config/prometheus/`, `config/grafana/dashboards/`, `scripts/slo_tracking.py`, `scripts/promotion_pipeline.py`, `scripts/platform_context_service.py`, `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`

## Scope

- add the canonical SLO catalog in `config/slo-catalog.json`
- add `scripts/slo_tracking.py` for shared catalog loading, Prometheus query evaluation, and SLO status rendering
- add `scripts/generate_slo_rules.py` to generate Prometheus rule files, file-based probe targets, and the Grafana SLO dashboard
- commit generated outputs under `config/prometheus/` and `config/grafana/dashboards/`
- wire the monitoring role to converge blackbox exporter plus Prometheus/Grafana SLO assets
- update the promotion gate to reject on low error budget or unevaluable SLO state
- expose `/v1/platform/slos` in the platform context service
- render an `SLO Status` section in the static ops portal
- document the operational workflow in `docs/runbooks/slo-tracking.md`

## Non-Goals

- Alert routing policy ownership beyond Prometheus-native rule definitions; ADR 0097 still owns notification routing.
- Automatic remediation based on burn rate.
- Claiming unrelated platform rollout outside the deliberate monitoring and ingress apply needed for this ADR's live surface.

## Expected Repo Surfaces

- `config/slo-catalog.json`
- `config/blackbox/blackbox.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/grafana/dashboards/slo-overview.json`
- `scripts/slo_tracking.py`
- `scripts/generate_slo_rules.py`
- `scripts/promotion_pipeline.py`
- `scripts/platform_context_service.py`
- `scripts/generate_ops_portal.py`
- `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`
- `docs/runbooks/slo-tracking.md`

## Expected Live Surfaces

- blackbox exporter and Prometheus rule groups active on `monitoring-lv3`
- Grafana `LV3 SLO Overview` dashboard imported and reachable
- `/v1/platform/slos` returns live error-budget state when the context service can reach Prometheus
- production promotions reject when any tracked SLO has less than 10% error budget remaining

## Verification

- `uv run --with pyyaml python scripts/generate_slo_rules.py --check`
- `uv run --with pytest --with fastapi --with qdrant-client --with pyyaml --with jsonschema python -m pytest tests/test_slo_tracking.py tests/test_platform_context_service.py tests/test_ops_portal.py tests/test_promotion_pipeline.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make syntax-check-monitoring`

## Merge Criteria

- committed generated SLO assets are up to date
- at least six SLOs are declared in the catalog
- the monitoring role converges blackbox exporter, Prometheus rule ingestion, and Grafana SLO dashboard import
- the promotion gate, ops portal, and platform context API all consume the same catalog-backed SLO status model

## Outcome

- repository implementation is complete on `main` in repo release `0.106.0`
- live apply completed on `2026-03-25` from `b203c2e`, with the monitoring converge passing on `monitoring-lv3` and the public Grafana edge controls re-rendered from repo state on `nginx-lv3`
- `platform_version` advances to `0.130.3` for the first live claim of ADR 0096
