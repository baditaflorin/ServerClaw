# ADR 0315: Canonical Page States And Next-Best-Action Guidance For Human Surfaces

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.140
- Implemented In Platform Version: 0.130.87
- Implemented On: 2026-04-02
- Date: 2026-03-31

## Context

The platform already has shared component and server-state ADRs, but users still
need a coherent experience when something is loading, empty, partially broken,
or successful.

Without a declared state model:

- one page may show a spinner forever while another shows a retry button
- permission failures may look like missing data
- empty states may provide no clue about what to do next
- success states may drop the user into a dead end after a governed action

## Decision

We will standardize first-party human-facing pages on a canonical state model
with explicit next-best-action guidance.

### Required state inventory

Every significant first-party page should define and test these states where
they apply:

- loading
- background refresh
- empty
- partial or degraded
- success
- validation error
- system error
- unauthorized or permission-limited
- not found

### Next-best-action rule

Every non-happy-path state must tell the user:

- what happened in plain language
- what they can safely do next
- where to find help, diagnostics, or recovery guidance

### Governance rule

State coverage belongs in shared component stories and browser tests so the
platform does not regress back into page-local improvisation.

## Consequences

**Positive**

- users get more predictable behavior across the workbench
- onboarding becomes easier because page outcomes are explained instead of
  implied
- success and failure flows stop ending in dead ends

**Negative / Trade-offs**

- teams must do more design work up front by enumerating page states
- overly generic state templates can become vague if pages do not supply the
  page-specific next action

## Boundaries

- This ADR does not prescribe exact copy strings or one universal component for
  every state.
- This ADR governs state behavior and guidance, not backend retry semantics.

## Related ADRs

- ADR 0234: Shared human app shell and navigation via PatternFly
- ADR 0236: Server-state and mutation feedback via TanStack Query
- ADR 0243: Component stories, accessibility, and UI contracts
- ADR 0313: Contextual help, glossary, and escalation drawer

## References

- [Shared Human App Shell And Navigation Via PatternFly](0234-shared-human-app-shell-and-navigation-via-patternfly.md)
- [Component Stories, Accessibility, And UI Contracts](0243-component-stories-accessibility-and-ui-contracts-via-storybook-playwright-and-axe-core.md)
