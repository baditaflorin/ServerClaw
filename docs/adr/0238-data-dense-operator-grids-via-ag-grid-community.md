# ADR 0238: Data-Dense Operator Grids Via AG Grid Community

- Status: Accepted
- Implementation Status: Implemented on workstream branch
- Implemented In Repo Version: 0.177.56
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Operators need high-density views for service inventories, receipts, drift
events, workflow runs, audit trails, backups, and dependency data. Plain HTML
tables and page-local JavaScript quickly become fragile when users need to:

- sort and filter large datasets
- pin and resize columns
- select rows for bulk actions
- page through large inventories
- navigate by keyboard

## Decision

We will use **AG Grid Community** as the default open source grid library for
first-party views that are fundamentally data-dense and operator-centric.

### Required grid capabilities

- sorting, filtering, pagination, and quick filter out of the box
- compact density suitable for operational data
- keyboard navigation and ARIA support
- shared column presets and formatting rules for timestamps, severity, state,
  and links

### Licensing rule

- default usage is the Community edition only
- Enterprise features require a separate ADR and cost justification

## Consequences

**Positive**

- complex data views can use a mature grid instead of custom table code
- users get consistent interaction patterns across inventories and audit views
- theming and compact density can be governed centrally

**Negative / Trade-offs**

- AG Grid introduces a substantial UI dependency
- teams must learn the grid model instead of sprinkling custom table helpers

## Boundaries

- This ADR applies to data-dense operational views, not simple static tables in
  docs or marketing-style pages.
- If a small table does not need grid behavior, plain HTML or PatternFly table
  components remain acceptable.

## Related ADRs

- ADR 0117: Dependency-graph runtime
- ADR 0121: Local search and indexing fabric
- ADR 0179: Service redundancy tier matrix
- ADR 0209: Use-case services and thin delivery adapters

## References

- <https://www.ag-grid.com/javascript-data-grid/key-features/>
- <https://www.ag-grid.com/javascript-data-grid/supported-browsers/>
