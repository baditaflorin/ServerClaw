# ADR 0240: Operator Visualization Panels Via Apache ECharts

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Human users need more than tables and text. The platform exposes health,
capacity, dependency, rollout, and incident data that is easier to understand
when rendered as timelines, status charts, topology diagrams, and compact
sparklines.

If each page invents its own charting approach, appearance and interaction will
drift and accessibility will be inconsistent.

## Decision

We will use **Apache ECharts** as the default charting and lightweight
visualization library for first-party inline operator panels.

### Preferred use cases

- compact trend charts and sparklines inside operational pages
- dependency, topology, and rollout timelines that are too dynamic for static
  SVGs
- card-level visual summaries that should feel native to the app shell

### Division of responsibilities

- ECharts is for embedded first-party product UX
- Grafana remains the dedicated observability product for full dashboards and
  exploratory metrics work

## Consequences

**Positive**

- first-party pages get one consistent visualization engine
- charts can share themes, colors, and state cues with the wider app shell
- ECharts supports richer interaction than ad hoc SVG or canvas helpers

**Negative / Trade-offs**

- complex chart configuration still requires discipline and review
- some users may expect Grafana-like freedom where a product page only needs a
  focused embedded chart

## Boundaries

- This ADR does not replace Grafana for observability-heavy analysis.
- If a table or textual status is clearer than a chart, use the simpler surface.

## Related ADRs

- ADR 0096: SLO tracking
- ADR 0105: Platform capacity model
- ADR 0117: Dependency-graph runtime
- ADR 0196: Realtime metrics

## References

- <https://echarts.apache.org/handbook/en/get-started/>
