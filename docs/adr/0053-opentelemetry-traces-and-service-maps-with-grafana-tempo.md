# ADR 0053: OpenTelemetry Traces And Service Maps With Grafana Tempo

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: 0.51.0
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Metrics show resource pressure and logs show local events, but neither gives a clear picture of request paths or multi-step automation flows.

That gap matters for:

- reverse-proxy to app request tracing
- internal API latency debugging
- agent workflow step timing
- service dependency visualization
- failure isolation across several components

## Decision

We will add distributed tracing and service-map support with OpenTelemetry and Grafana Tempo.

Initial design:

1. Tempo is added to the monitoring stack and viewed through Grafana.
2. New internal apps and automation entry points should prefer OpenTelemetry-compatible instrumentation.
3. A shared collector path handles trace ingestion, normalization, and export.
4. Service naming and environment tags are standardized so traces line up with dashboards, logs, and workflow metadata.

Initial trace candidates:

- NGINX edge to private application hops
- Windmill workflow executions
- internal control-plane APIs
- mail platform API requests
- agent tooling that chains several platform operations

## Consequences

- Operators gain a visual service graph instead of inferring call paths from logs.
- Agents can reason about where time or failure accumulates in a workflow.
- New apps need instrumentation expectations from day one.
- Trace volume and storage costs must be controlled deliberately.

## Boundaries

- Tempo is not a replacement for logs, metrics, or receipts.
- We do not need full tracing on every existing workload before shipping the first rollout.
- Public-facing applications must still follow the private-first API publication policy unless explicitly approved otherwise.

## Sources

- [Grafana Tempo configuration example](https://github.com/grafana/tempo/blob/v2.10.3/example/docker-compose/shared/tempo.yaml)
- [OpenTelemetry Collector configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Grafana Tempo release v2.10.3](https://github.com/grafana/tempo/releases/tag/v2.10.3)
- [OpenTelemetry Collector Contrib release v0.148.0](https://github.com/open-telemetry/opentelemetry-collector-contrib/releases/tag/v0.148.0)

## Implementation Notes

- `monitoring-lv3` now runs Prometheus, Tempo, and `otelcol-contrib` beside the existing Grafana and InfluxDB services.
- Grafana is provisioned with dedicated Prometheus and Tempo datasources so operators can inspect traces in Explore and render the built-in service map.
- The shared OTLP collector listens on `10.10.10.40:4317` and `10.10.10.40:4318` and forwards traces into the local Tempo backend.
- The first live producer is the private mail gateway on `docker-runtime-lv3`, instrumented for inbound FastAPI requests plus outbound `httpx` calls to Stalwart and Brevo.
- Standard resource tags now include `service.name`, `service.namespace=lv3`, and `deployment.environment=lv3` for the first rollout.
