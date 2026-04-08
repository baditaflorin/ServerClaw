# ADR 0307: Platform Workbench As The Cohesive First-Party App Frame

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.49
- Implemented In Platform Version: 0.130.35
- Implemented On: 2026-04-08
- Date: 2026-03-31

## Context

The platform already exposes a large set of useful human-facing surfaces:

- Homepage for discovery and service entry
- the ops portal for governed actions
- the docs portal for reference material
- Outline for living knowledge
- Plane for planning
- product-native surfaces such as Grafana, Paperless, Gitea, and JupyterHub

Those surfaces share infrastructure, identity, and domain conventions, but they
still risk feeling like a loose collection of tools instead of one coherent
application:

- users must remember which product owns which task
- onboarding still starts from product names more often than user intent
- shared navigation, help, notification, and recovery patterns are defined
  only partially across first-party surfaces

The next usability step is not another isolated screen. The platform needs a
declared product frame that explains how all human-facing surfaces fit together
as one experience.

## Decision

We will treat the platform's human-facing experience as one cohesive
**Platform Workbench** rather than as a loose set of unrelated tools.

### Workbench surface classes

Every human-facing surface must declare one of these roles in the overall app:

- **Home surfaces** orient the user, show attention items, and route them to
  the next useful task
- **Task surfaces** let the user complete a governed action, workflow, or
  operational job
- **Reference surfaces** explain how the platform works and how to recover it
- **Product-native surfaces** remain valid when a third-party product provides
  the best UX, but they must still enter and exit through the workbench model

### Cohesion rules

- one authenticated product identity across first-party surfaces
- one shared app-shell vocabulary and navigation model
- one launcher, notification, help, and escalation story
- one expectation that a user can start in a home surface, act in a task
  surface, and learn or recover through a reference surface without losing
  context

### Modeling rule

New human-facing ADRs must describe where the new surface sits in the
workbench, how users arrive there, what task it owns, and where the user goes
next after success, failure, or interruption.

## Consequences

**Positive**

- the platform finally has a single human product story that matches the
  repository's technical integration story
- onboarding, navigation, and user-flow work can build on one shared frame
  instead of starting from product-local assumptions
- future service additions can be evaluated on how they fit the workbench, not
  only on whether they run

**Negative / Trade-offs**

- every future human-facing change now carries a higher information-architecture
  bar; "just add another link" is no longer enough
- the workbench model creates documentation and UX governance work even when no
  new runtime code ships yet

## Boundaries

- This ADR does not require embedding every third-party product inside one
  browser shell.
- This ADR does not replace product-native UIs where they are clearly better.
- This ADR defines the cohesive app frame, not the detailed component or state
  libraries already covered by the ADR 0234-0243 UX bundle.

## Related ADRs

- ADR 0093: Interactive ops portal with live actions
- ADR 0094: Developer portal and documentation site
- ADR 0152: Homepage for unified service dashboard
- ADR 0209: Use-case services and thin delivery adapters
- ADR 0234: Shared human app shell and navigation via PatternFly
- ADR 0235: Cross-application launcher and favorites

## References

- `https://home.lv3.org`
- `https://ops.lv3.org`
- `https://docs.lv3.org`
