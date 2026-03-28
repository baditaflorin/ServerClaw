# ADR 0250: Log Ingestion And Queryability Canaries Via Loki Canary

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.57
- Implemented In Platform Version: 0.130.44
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

ADR 0169 made logs more structured, but an operator still needs proof that logs
from each environment are actually arriving in the central store and can be
queried there.

Without an end-to-end canary:

- local logs can exist while central ingestion is broken
- one environment can silently stop shipping logs
- the logging path can fail without a fast, unambiguous operational signal

## Decision

We will use **Loki Canary** as the default end-to-end log-path assurance signal
for the central logging pipeline.

### Required behavior

- each assurance-scoped environment must emit a recurring canary stream
- the canary must prove both write-path and query-path correctness
- canary results must be visible in operator dashboards and the runtime
  assurance rollup

### Relationship to structured logging

- structured log contracts remain the content standard
- Loki Canary proves the transport and query path, not the field schema itself

## Consequences

**Positive**

- central logging failures become easy to detect quickly
- “loggable” gains a concrete, repeatable meaning
- operators can distinguish app failure from log-pipeline failure more clearly

**Negative / Trade-offs**

- the platform now owns another recurring telemetry stream
- canary noise must be clearly separated from normal application logs

## Boundaries

- This ADR proves end-to-end logging reachability; it does not validate every
  application field or retention query shape.
- Third-party SaaS log sinks remain outside the assurance contract unless they
  are explicitly adopted.

## Related ADRs

- ADR 0052: Grafana Loki
- ADR 0169: Structured log field contract
- ADR 0244: Runtime assurance matrix per service and environment

## References

- <https://grafana.com/docs/loki/latest/operations/loki-canary/>
