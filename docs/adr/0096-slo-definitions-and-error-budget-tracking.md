# ADR 0096: SLO Definitions and Error Budget Tracking

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.106.0
- Implemented In Platform Version: 0.130.3
- Implemented On: 2026-03-25
- Date: 2026-03-23

## Context

The platform has monitoring, dashboards, and health probe contracts, but it still lacked a machine-readable definition of acceptable reliability. Operators could tell whether a service was healthy right now, but not whether it had been reliable over a rolling window or whether a recent incident had consumed most of the platform's remaining error budget.

That gap showed up in three places:

- Grafana and health probes exposed current status but not an explicit reliability target.
- The promotion gate in ADR 0073 checked staged health and approval state, but not whether the platform was already operating with a nearly exhausted error budget.
- The operator surface had no single catalog that tied service objectives, Prometheus expressions, alerts, and dashboards together.

## Decision

We will define SLOs in a canonical catalog, derive Prometheus rules and Grafana dashboard assets from that catalog, probe the declared SLO targets with a local blackbox exporter on the monitoring VM, and surface error budget posture through both the promotion gate and the platform context API.

### Canonical SLO catalog

SLOs live in [`config/slo-catalog.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/slo-catalog.json). Each entry binds:

- a `service_id`
- an `indicator` (`availability` or `latency`)
- an `objective_percent`
- a rolling `window_days`
- a `target_url` for the blackbox probe
- a `probe_module`
- an optional `latency_threshold_ms`

The initial catalog covers the public and control-plane-adjacent surfaces that already have clear health contracts: Grafana, Keycloak availability and latency, Uptime Kuma, NGINX edge, Open WebUI, Windmill, NetBox, and the platform context API.

### Generated Prometheus assets

[`scripts/generate_slo_rules.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/generate_slo_rules.py) reads the catalog and commits four generated assets:

- [`config/prometheus/rules/slo_rules.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/prometheus/rules/slo_rules.yml)
- [`config/prometheus/rules/slo_alerts.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/prometheus/rules/slo_alerts.yml)
- [`config/prometheus/file_sd/slo_targets.yml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/prometheus/file_sd/slo_targets.yml)
- [`config/grafana/dashboards/slo-overview.json`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/grafana/dashboards/slo-overview.json)

The monitoring role now copies those assets to the monitoring VM, enables a local `prometheus-blackbox-exporter`, and configures Prometheus to:

- probe the catalog targets via file-based service discovery
- record rolling success ratios, error rates, error-budget remaining, burn rate, and projected budget exhaustion
- publish burn-rate and low-budget alerts as Prometheus-native alerting rules

### Dashboard and operator surfaces

Grafana now imports a dedicated `LV3 SLO Overview` dashboard built from the same catalog. Each SLO gets:

- a 30-day compliance stat
- error budget remaining
- 1-hour burn rate
- projected days to budget exhaustion

The static ops portal generator now renders an `SLO Status` section, and the platform context service exposes [`/v1/platform/slos`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/platform_context_service.py) so the ADR 0093 interactive portal can consume the same machine-readable view.

### Promotion gate integration

[`scripts/promotion_pipeline.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/promotion_pipeline.py) now evaluates SLO posture before approving a production promotion. The gate rejects when:

- the SLO query path cannot be evaluated
- required SLO metric samples are missing
- any SLO reports less than 10% error budget remaining

This keeps the promotion contract aligned with platform reliability instead of only point-in-time health.

## Consequences

**Positive**

- Reliability targets are now explicit, versioned, and generated from one source of truth.
- Adding or changing an SLO updates Prometheus rules, probe targets, and the Grafana dashboard together.
- Promotion decisions can now block on exhausted error budgets instead of only on failed staging receipts.
- The operator portals and API surfaces can talk about reliability with concrete numbers instead of prose.

**Negative / Trade-offs**

- The new rule set adds blackbox probe traffic and additional Prometheus series on the monitoring VM.
- Initial objective percentages are still estimates and should be reviewed after a sustained production data window.
- The promotion gate is now stricter; if the SLO query path is unavailable, promotion is rejected rather than silently bypassed.

## Alternatives Considered

- **Uptime Kuma percentages alone**: useful for raw uptime history, but insufficient for burn-rate alerting, code generation, and promotion-gate enforcement.
- **A separate SLO platform such as Pyrra or Nobl9**: richer, but additional moving parts for a small single-site platform where Prometheus-native rules are sufficient.
- **Document-only targets in ADR text**: easy to write, but impossible to validate or consume automatically.

## Related ADRs

- ADR 0011: Monitoring VM with Grafana and Proxmox metrics
- ADR 0064: Health probe contracts for all services
- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0092: Unified platform API gateway
- ADR 0093: Interactive ops portal
- ADR 0097: Alerting routing and on-call runbook model

## Outcome

- repository implementation became true on `main` in repo release `0.106.0`
- live platform implementation became true on `2026-03-25` in platform version `0.130.3`
- `monitoring-lv3` now runs the repo-managed `prometheus-blackbox-exporter`, the generated `slo-rules.yml` and `slo-alerts.yml` rule sets, and the `LV3 SLO Overview` Grafana dashboard verification contract
- the public Grafana edge verification that protects the SLO dashboard path is aligned live again: dashboard URLs redirect unauthenticated viewers to login and `https://grafana.lv3.org/api/health` returns `404`
