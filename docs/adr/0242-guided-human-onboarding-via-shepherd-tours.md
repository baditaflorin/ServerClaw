# ADR 0242: Guided Human Onboarding Via Shepherd Tours

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The platform now has enough moving parts that a new human user can land in
Homepage, the ops portal, Outline, Plane, or a product-native screen and still
not understand:

- what to do first
- where to find role-specific actions
- which pages are reference-only versus action-capable

The repository already carries onboarding and runbook content, but first-run UX
inside the application surfaces is still too implicit.

## Decision

We will use **Shepherd.js** for guided first-run tours, contextual onboarding,
and major-feature walkthroughs in first-party browser surfaces.

### Tour rules

- tours must be role-aware and task-oriented, not generic product marketing
- tours must be dismissible, resumable, and safe to skip
- each tour step should link to the authoritative runbook or reference page when
  deeper explanation is needed
- keyboard navigation and focus behavior are required, not optional

## Consequences

**Positive**

- new operators can learn the platform in the flow of work
- product changes can ship with contextual guidance instead of relying only on
  changelog reading
- the platform reduces dependence on a live human mentor for first-day use

**Negative / Trade-offs**

- tours require ongoing maintenance as pages evolve
- a bad tour can be more annoying than helpful if it becomes noisy or outdated

## Boundaries

- This ADR does not replace onboarding documentation, runbooks, or direct human
  training.
- Tours should be used sparingly for meaningful transitions, not for every page
  decoration.

## Related ADRs

- ADR 0108: Operator onboarding and offboarding
- ADR 0152: Homepage for unified service dashboard
- ADR 0199: Outline living knowledge wiki

## References

- <https://www.shepherdjs.dev/>
