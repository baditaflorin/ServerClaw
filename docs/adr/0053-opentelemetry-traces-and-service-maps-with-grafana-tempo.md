# ADR 0053: OpenTelemetry Traces And Service Maps With Grafana Tempo

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
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
