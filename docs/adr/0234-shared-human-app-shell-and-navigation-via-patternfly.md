# ADR 0234: Shared Human App Shell And Navigation Via PatternFly

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.72
- Implemented In Platform Version: 0.130.50
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

Human users currently experience the platform through several distinct surfaces:
Homepage for discovery, the ops portal for platform actions, the docs portal
for reference material, Outline for living knowledge, Plane for task tracking,
and product-native screens such as Grafana or Keycloak.

Those surfaces are useful, but the first-party parts still risk feeling like a
collection of separate tools rather than one coherent product:

- page chrome, spacing, empty states, and error states are inconsistent
- responsive behavior is not governed as one shared contract
- common navigation elements are at risk of being hand-built more than once

The platform needs a production-ready visual and navigational foundation that
reduces custom UI work and gives future human-facing apps one consistent shell.

## Decision

We will use **PatternFly** as the default open source app-shell and design
system for first-party browser surfaces that require shared navigation, page
layout, global utility actions, and responsive operator workflows.

### Required shell elements

- masthead with product identity, help, notifications, and user menu
- responsive primary navigation with desktop and mobile behavior
- shared page templates for dashboards, detail pages, forms, and empty states
- shared status, severity, skeleton, error, and unauthorized-state components

### Scope

- new rich first-party browser surfaces should prefer PatternFly components over
  hand-coded page chrome
- existing surfaces may migrate incrementally as they are touched
- third-party products keep their native UI, but our shell should deep-link to
  them in a consistent way

## Consequences

**Positive**

- human users get one coherent visual language across first-party surfaces
- accessibility, responsive layout, and common enterprise patterns come from a
  mature upstream system instead of repo-local reinvention
- future pages can assemble from approved primitives instead of bespoke HTML and
  CSS

**Negative / Trade-offs**

- first-party UI work now depends on a larger frontend component system
- incremental migration is required before the full platform feels unified

## Boundaries

- This ADR does not require replacing Homepage, Outline, Plane, Grafana, or
  other product-native UIs.
- This ADR governs the shell and shared primitives, not the business logic or
  API contracts behind each page.

## Related ADRs

- ADR 0093: Interactive ops portal with live actions
- ADR 0094: Developer portal and documentation site
- ADR 0133: Portal authentication by default
- ADR 0152: Homepage for unified service dashboard
- ADR 0209: Use-case services and thin delivery adapters

## References

- <https://www.patternfly.org/components/masthead/design-guidelines/>
- <https://www.patternfly.org/components/navigation/>
