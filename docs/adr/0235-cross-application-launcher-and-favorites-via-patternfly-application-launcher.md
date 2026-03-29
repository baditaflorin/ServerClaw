# ADR 0235: Cross-Application Launcher And Favorites Via PatternFly Application Launcher

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The monolithic platform already exposes many useful destinations, but human
navigation is still too memory-driven:

- Homepage is the discovery dashboard
- the ops portal is action-oriented
- Outline, Plane, Grafana, Windmill, and other products solve specialized jobs

Users should not need to remember which surface owns which task, nor keep a
collection of bookmarks to move around the platform efficiently.

## Decision

We will standardize on the **PatternFly Application Launcher** as the default
cross-application switcher for first-party browser surfaces.

### Launcher behavior

- render from the canonical service, subdomain, workflow, and persona catalogs
- support searchable application lists, favorites, and recent destinations
- group destinations by user-facing purpose such as operate, observe, learn,
  plan, and administer
- live in the shared masthead so switching context is always one click away

### Separation of roles

- Homepage remains the broad service dashboard and onboarding landing page
- the launcher is the fast-switch surface for already-authenticated users
- local search remains responsible for content discovery inside docs and
  knowledge surfaces

## Consequences

**Positive**

- cross-surface movement becomes fast, predictable, and learnable
- favorites reduce friction for frequent operator paths
- navigation stays DRY because one upstream component and one repo catalog drive
  the launcher

**Negative / Trade-offs**

- the launcher is only as useful as the catalog metadata behind it
- users now depend on good information architecture decisions, not just raw URL
  lists

## Boundaries

- This ADR does not replace content search, docs search, or API search.
- This ADR does not require embedding every product inside one page shell;
  deep-linking remains valid when a product owns its own UX.

## Related ADRs

- ADR 0075: Service capability catalog
- ADR 0121: Local search and indexing fabric
- ADR 0152: Homepage for unified service dashboard
- ADR 0193: Plane task-board automation
- ADR 0199: Outline living knowledge wiki

## References

- <https://www.patternfly.org/components/menus/application-launcher/design-guidelines/>
- <https://www.patternfly.org/components/masthead/design-guidelines/>
