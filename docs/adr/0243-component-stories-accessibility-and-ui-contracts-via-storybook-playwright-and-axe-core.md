# ADR 0243: Component Stories, Accessibility, And UI Contracts Via Storybook, Playwright, And Axe-Core

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

If the platform adopts richer human-facing UI, it also needs a safe way to
evolve that UX:

- components should have canonical examples and documented states
- accessibility regressions should be detected automatically
- cross-browser issues should be tested before users discover them
- future agent-facing work will benefit from stable, inspectable UI contracts

Without a component workbench and automated checks, the repo will drift back
toward hand-coded one-off pages.

## Decision

We will use **Storybook** for component stories and docs, **Playwright** for
cross-browser interaction testing, and **axe-core** for automated accessibility
checks in the UI test stack.

### Required practices

- shared components must ship with stories for normal, empty, loading, error,
  and permission-limited states where applicable
- browser tests must cover the most important human journeys, not just render
  smoke tests
- accessibility scanning should run in CI with documented waivers when issues
  are temporarily accepted

### Secondary benefit

Story-driven component documentation will also create a stronger foundation for
future agent and LLM onboarding because the UI states become explicit and
repeatable instead of living only in screenshots or tribal knowledge.

## Consequences

**Positive**

- UI changes become reviewable in isolation before they land in product pages
- accessibility and browser behavior get a governed test surface
- component docs become an onboarding aid for both humans and future agents

**Negative / Trade-offs**

- story maintenance and UI test execution add cost to the delivery pipeline
- teams must keep stories aligned with real production states

## Boundaries

- This ADR does not replace end-to-end product testing or manual accessibility
  review.
- Automated accessibility checks are necessary but not sufficient for inclusive
  UX.

## Related ADRs

- ADR 0133: Portal authentication by default
- ADR 0168: Automated validation gate
- ADR 0209: Use-case services and thin delivery adapters

## References

- <https://storybook.js.org/docs/>
- <https://playwright.dev/docs/intro>
- <https://playwright.dev/docs/accessibility-testing>
- <https://www.deque.com/axe/core-documentation/>
