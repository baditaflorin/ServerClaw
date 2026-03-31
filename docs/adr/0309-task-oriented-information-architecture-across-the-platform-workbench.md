# ADR 0309: Task-Oriented Information Architecture Across The Platform Workbench

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-31

## Context

As more platform services are integrated, navigation by product name alone stops
being friendly:

- Homepage shows what exists
- the launcher shows where things are
- docs explain how the pieces fit
- product-native screens still use their own labels

That is workable for experienced operators who already know the stack. It is
not good enough for onboarding or for interrupted work, because users have to
translate their intent into a product map before they can act.

The platform needs a declared information architecture based on user tasks, not
just on infrastructure nouns.

## Decision

We will organize first-party navigation and routing around five task-oriented
lanes:

| Lane | Primary question it answers |
| --- | --- |
| `Start` | Where do I begin and what needs my attention? |
| `Observe` | What is happening right now? |
| `Change` | How do I make a safe governed change? |
| `Learn` | Where is the explanation, runbook, or reference? |
| `Recover` | How do I restore, repair, or escalate? |

### Required mapping rule

Every first-party page must declare:

- one primary lane
- optional secondary lanes for cross-linking and breadcrumbs
- the "next likely lane" after success and after failure

### Catalog rule

Service, runbook, and launcher catalogs may still expose product names, but
they must also carry the user-facing task lane so navigation, search, help, and
home surfaces can route by intent instead of only by product.

### Copy rule

Primary navigation labels should prefer the lane names over internal service
brands. Product names remain visible inside cards, detail pages, and launch
targets where precision matters.

## Consequences

**Positive**

- onboarding becomes more intuitive because users can navigate from intent
  rather than memorized product ownership
- the launcher, help drawer, command palette, and home surfaces can all share
  one routing taxonomy
- future services fit into a stable user-flow model even when their native UI
  is different

**Negative / Trade-offs**

- lane assignment requires real curation; some surfaces legitimately span more
  than one lane
- experienced users who think in product names may need a transition period

## Boundaries

- This ADR does not ban product names; it governs primary orientation, not the
  detailed labels inside each product.
- This ADR does not replace the service-capability catalog or the subdomain
  catalog; it adds a user-flow layer above them.

## Related ADRs

- ADR 0075: Service capability catalog
- ADR 0093: Interactive ops portal with live actions
- ADR 0094: Developer portal and documentation site
- ADR 0152: Homepage for unified service dashboard
- ADR 0235: Cross-application launcher and favorites
- ADR 0239: Browser-local search experience via Pagefind

## References

- [Homepage For Unified Service Dashboard](0152-homepage-for-unified-service-dashboard.md)
- [Shared Human App Shell And Navigation Via PatternFly](0234-shared-human-app-shell-and-navigation-via-patternfly.md)
