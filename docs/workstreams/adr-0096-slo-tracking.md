# Workstream ADR 0096: SLO Definitions and Error Budget Tracking

- ADR: [ADR 0096](../adr/0096-slo-definitions-and-error-budget-tracking.md)
- Title: Machine-readable SLO catalog with Prometheus recording rules, multi-window burn rate alerts, and error budget panels in Grafana
- Status: ready
- Branch: `codex/adr-0096-slo-tracking`
- Worktree: `../proxmox_florin_server-slo-tracking`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0064-health-probes`, `adr-0073-promotion-gate`, `adr-0092-platform-api-gateway`
- Conflicts With: none
- Shared Surfaces: `config/grafana/`, Prometheus/Grafana on `monitoring-lv3`, `scripts/` (promotion gate)

## Scope

- write `config/slo-catalog.json` — SLO definitions for all edge-published and control-plane services
- write `scripts/generate_slo_rules.py` — reads the catalog and generates Prometheus recording rules and Alertmanager alert rules
- write `config/grafana/provisioning/rules/slo_rules.yml` (generated output; committed)
- write `config/alertmanager/rules/slo_alerts.yml` (generated output; committed)
- write Grafana dashboard `config/grafana/dashboards/slo-overview.json` — one row per SLO with error budget panel
- update `scripts/promotion_pipeline.py` — add `check_slo_gate()` function that blocks promotion when error budget < 10%
- add `make generate-slo-rules` target to Makefile
- add SLO status section to ops portal integration notes (for ADR 0093 to consume `/v1/platform/slos` endpoint)
- add `/v1/platform/slos` endpoint to the API gateway

## Non-Goals

- SLOs for internal-only services (Postgres, OpenBao, step-ca) in this iteration — covered by health probes; SLOs added for user-facing services first
- Automated error budget burn rate response (auto-scaling, circuit breaking) — detection only

## Expected Repo Surfaces

- `config/slo-catalog.json`
- `scripts/generate_slo_rules.py`
- `config/grafana/provisioning/rules/slo_rules.yml`
- `config/alertmanager/rules/slo_alerts.yml`
- `config/grafana/dashboards/slo-overview.json`
- `scripts/promotion_pipeline.py` (patched: SLO gate added)
- Makefile (patched: `make generate-slo-rules`)
- `docs/adr/0096-slo-definitions-and-error-budget-tracking.md`
- `docs/workstreams/adr-0096-slo-tracking.md`

## Expected Live Surfaces

- Grafana `SLO Overview` dashboard is accessible and shows error budget for each service
- All SLO recording rules are active in Prometheus (verify via `prometheus/api/v1/rules`)
- Burn rate alerts are configured in Alertmanager
- `lv3 promote --env production` is blocked when any SLO has < 10% error budget

## Verification

- SLO recording rules query returns non-null values for `slo:keycloak_availability:budget_remaining`
- Grafana SLO Overview dashboard loads without errors and shows > 0% error budget for all services
- Manually lower the Keycloak probe interval to force a missed probe; verify a `SLOFastBurn` alert appears in Alertmanager within 5 minutes; restore probe interval
- Promotion gate blocks when `slo:keycloak_availability:budget_remaining < 0.10` (test by temporarily lowering the threshold)

## Merge Criteria

- `make generate-slo-rules` exits 0 and produces valid YAML
- SLO Overview dashboard deployed to Grafana and showing live data
- At least 6 SLOs defined (one per edge-published service)
- Alertmanager has the burn rate alerts configured
- Promotion gate SLO check is active

## Notes For The Next Assistant

- Prometheus recording rules require the `interval` field in the rule group to be set to `60s` to match the health probe scrape interval; mismatched intervals produce incorrect `avg_over_time` calculations
- The `slo:<id>:budget_remaining` metric uses a 30-day window computed from 1-minute samples; `sum_over_time([30d:1m])` generates 43,200 data points per evaluation — this is heavy; ensure the recording rule runs at most every 5 minutes
- The SLO dashboard row for each service should include a "time to budget exhaustion" panel computed as `(budget_remaining / burn_rate) * 30d` — this is the most actionable number for an operator
- Initial SLO targets are estimates; add a note in `config/slo-catalog.json` that targets should be reviewed after 30 days of data collection
