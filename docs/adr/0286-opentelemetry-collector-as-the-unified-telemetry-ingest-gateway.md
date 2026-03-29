# ADR 0286: OpenTelemetry Collector As The Unified Telemetry Ingest Gateway

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

Platform services currently push metrics to Prometheus via scrape endpoints
and emit logs in inconsistent formats. There is no unified entry point for
traces, and application services that emit structured telemetry must be
individually configured to point at the correct backend (Prometheus,
Loki, a future tracing backend). This creates two problems:

- **Tight coupling between instrumentation and backend**: changing the metrics
  backend or adding a tracing sink requires modifying every service's
  configuration, not a single pipeline definition.
- **No API contract for telemetry ingestion**: each service speaks a
  different protocol (Prometheus scrape, syslog, JSON file). There is no
  single, documented endpoint that a service can call to deliver all
  telemetry signal types.

OpenTelemetry Collector (otelcol) is a CPU-only, vendor-agnostic telemetry
pipeline. It accepts OTLP/gRPC and OTLP/HTTP as its primary ingest APIs—both
carry traces, metrics, and logs in a single protocol with a versioned protobuf
schema. The collector is configured entirely via a YAML pipeline file; there
is no GUI. Any service that speaks OTLP points at one endpoint; the collector
routes signals to whatever backends are configured without the service needing
to know about them.

## Decision

We will deploy **OpenTelemetry Collector** as the unified telemetry ingest
gateway for all platform services.

### Deployment rules

- The collector runs as a Docker Compose service on the docker-runtime VM
  using the `otel/opentelemetry-collector-contrib` image, which includes the
  full set of receivers, processors, and exporters
- It is internal-only; no public subdomain is issued
- The collector listens on:
  - `4317/tcp` — OTLP/gRPC (primary ingest API for instrumented services)
  - `4318/tcp` — OTLP/HTTP (alternative ingest for services without gRPC
    support or browser-side SDKs)
  - `8888/tcp` — collector's own Prometheus metrics endpoint (scraped by the
    platform Prometheus instance)
- The pipeline configuration is managed as an Ansible-rendered template;
  changes to receivers, processors, or exporters are applied by restarting
  the container with the new config
- No secrets are required for unauthenticated internal ingest; authenticated
  exporters (e.g. remote write targets) retrieve credentials from OpenBao
  (ADR 0077) via environment variable injection

### API contract rules

- All platform services that emit telemetry **must** target the collector's
  OTLP endpoint as their exporter; direct-to-backend exporter configuration
  (e.g. a service writing directly to a remote Prometheus or Loki endpoint)
  is prohibited
- The OTLP/gRPC API is the preferred transport; OTLP/HTTP is used only for
  runtimes where gRPC is not available (browser JavaScript, some embedded
  runtimes)
- The OTLP protobuf schema version is the API contract; services must use
  an OpenTelemetry SDK at a version compatible with the collector's OTLP
  receiver version; the collector image version is pinned and promoted through
  the standard ADR 0269 freshness gates
- Receivers for legacy protocols (Prometheus scrape, Jaeger, Zipkin) are
  enabled in the collector config as translation shims for services that
  cannot be refactored to emit OTLP; they are treated as technical debt and
  tracked for removal

### Pipeline topology rules

- The collector pipeline is structured as:
  `receivers → batch processor → exporters`
- Metrics are exported to the platform Prometheus instance via the
  `prometheusremotewrite` exporter
- Traces are exported to the platform tracing backend via the `otlp` exporter
- Logs are exported to Loki via the `loki` exporter
- The batch processor is configured to flush at 8192 spans or 10 seconds,
  whichever comes first, to bound memory usage

## Consequences

**Positive**

- A service developer configures one OTLP endpoint and one SDK; all three
  signal types (metrics, traces, logs) are delivered without additional
  per-signal configuration.
- The backend topology is entirely in the collector config; swapping a metrics
  backend requires one config change and a container restart, not a
  coordinated update across all instrumented services.
- The OTLP protobuf schema is a versioned, machine-readable API contract;
  breaking changes are detectable before promotion.
- The collector's own metrics expose pipeline health (dropped spans, export
  errors, queue depth) via the Prometheus endpoint—no separate monitoring
  agent is needed.

**Negative / Trade-offs**

- The collector is a synchronous dependency for telemetry delivery; if it
  is unavailable, services that use synchronous OTLP exporters will back-
  pressure or drop spans. Services must use asynchronous batch exporters
  with a local retry queue.
- Adding a new exporter requires a collector config change and container
  restart; this is a minor operational event but it is not zero-touch.

## Boundaries

- The collector is the telemetry ingest gateway; it does not store telemetry.
  Storage and querying remain in Prometheus (metrics), Loki (logs), and the
  tracing backend (traces).
- The collector does not replace the Prometheus scrape model for services
  that expose a `/metrics` endpoint and cannot be refactored; those are
  handled via the Prometheus receiver shim.
- Alert evaluation and notification routing are not performed by the
  collector; they remain in the Prometheus alertmanager pipeline.
- The collector's config file is not a runtime-editable API; it is managed
  by Ansible and changes go through version control.

## Related ADRs

- ADR 0077: Compose secrets injection pattern
- ADR 0096: SLO probes and Blackbox exporter
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://opentelemetry.io/docs/collector/>
- <https://opentelemetry.io/docs/specs/otlp/>
