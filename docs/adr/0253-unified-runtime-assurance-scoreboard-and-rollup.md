# ADR 0253: Unified Runtime Assurance Scoreboard And Rollup

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Once the platform has existence witnesses, richer health states, browser
journeys, HTTPS checks, log canaries, smoke suites, and route assertions, the
operator still needs one place to answer the practical question:

“Which services in which environments are actually safe for humans to trust
right now?”

## Decision

We will publish a **unified runtime assurance scoreboard** that rolls the
assurance matrix into one operator-facing view.

### Required rollup fields

- service and environment identity
- assurance dimensions with pass, degraded, failed, or unknown state
- last verified timestamp per dimension
- owning team, runbook, and next action when red

### Rollup rules

- a service may be shown as overall healthy only when all stage-required
  dimensions pass
- unknown is never silently treated as healthy
- degraded must remain visible as degraded, not collapsed into green

## Consequences

**Positive**

- operators get one honest answer instead of six disconnected dashboards
- stage readiness becomes visible at portfolio scale
- weak or missing assurance is exposed explicitly instead of being hidden by
  partial green signals

**Negative / Trade-offs**

- rollup logic can oversimplify if the per-dimension rules are careless
- users may over-trust the scoreboard unless runbooks remain easy to drill into

## Boundaries

- This ADR defines the rollup and operator surface, not the implementation tool.
- The scoreboard summarizes assurance; it does not replace source evidence,
  receipts, logs, or runbooks.

## Related ADRs

- ADR 0093: Interactive ops portal with live actions
- ADR 0113: World-state materializer
- ADR 0123: Service uptime contracts and monitor-backed health
- ADR 0244: Runtime assurance matrix per service and environment
