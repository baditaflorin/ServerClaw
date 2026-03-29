# ADR 0236: Server-State And Mutation Feedback Via TanStack Query

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.81
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Human-facing apps need reliable behavior for loading, retrying, refreshing, and
invalidating server data. If every page hand-codes its own fetch lifecycle, the
user experience becomes inconsistent:

- one page quietly shows stale data while another blocks on every refresh
- mutation success and failure states drift between products
- polling, background refresh, and optimistic updates become ad hoc

The platform already exposes structured APIs and use-case services, so the
browser layer should use a mature server-state library instead of custom fetch
plumbing.

## Decision

We will use **TanStack Query** as the default server-state and mutation-feedback
layer for interactive first-party React surfaces.

### Required usage patterns

- query keys must map to canonical resources or use-case outputs
- mutations must declare invalidation behavior instead of forcing full-page
  refreshes
- loading, stale, error, and retry states must be rendered explicitly
- background polling and refresh cadence must be deliberate for operational
  pages

## Consequences

**Positive**

- browser data behavior becomes more consistent across the platform
- caching, retries, background updates, and mutation flows reuse a mature
  library instead of page-local code
- stale-data warnings become easier to govern for operator-critical pages

**Negative / Trade-offs**

- teams need shared conventions for query keys, invalidation, and polling
- not every page needs optimistic UX, so some discipline is required to avoid
  over-engineering

## Boundaries

- This ADR governs server state, not local component state such as transient
  dialogs or view toggles.
- Streaming, event, or websocket-heavy surfaces may still require specialized
  adapters above or beside TanStack Query.

## Related ADRs

- ADR 0092: Unified platform API gateway
- ADR 0206: Ports and adapters for external integrations
- ADR 0209: Use-case services and thin delivery adapters

## References

- <https://tanstack.com/query/latest>
