# ADR 0311: Global Command Palette And Universal Open Dialog Via cmdk

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.142
- Implemented In Platform Version: 0.130.90
- Implemented On: 2026-04-02
- Date: 2026-03-31

## Context

Even with a better launcher and task-oriented navigation, experienced users
still lose time hunting for the right destination:

- a runbook may be easier to find from search than from primary navigation
- a service may be known by capability, not by product name
- an operator may want to jump directly to a frequent action or recent page

The platform already intends to ship richer first-party React surfaces and has
Pagefind, launcher metadata, and service catalogs available as search inputs.
What is missing is one keyboard-first universal open flow that works the same
way everywhere.

## Decision

We will use **cmdk** as the default global command palette and universal open
dialog for first-party React surfaces.

### Palette capabilities

The palette must support:

- opening applications, pages, and recent destinations
- searching runbooks, docs, and glossary entries
- surfacing permission-allowed quick actions such as health checks or safe
  deep links into governed workflows
- filtering and grouping results by task lane and destination type

### Source precedence

Palette results should draw from:

1. recent destinations and user favorites
2. launcher and service-catalog destinations
3. docs and runbook search results
4. permitted quick actions

### Safety rule

Destructive or high-risk actions may be discovered in the palette, but they
must still route into their full confirmation flow. The palette is a fast way
to open work, not a shortcut around governance.

## Consequences

**Positive**

- frequent users get a fast, low-friction way to move across the workbench
- onboarding improves because a user can search by intent, not only by
  navigation memory
- the same command surface can unify discovery across apps, docs, and actions

**Negative / Trade-offs**

- command quality depends on good search metadata and naming discipline
- a palette with too many low-value commands quickly becomes noise

## Boundaries

- This ADR does not replace primary navigation or the application launcher.
- This ADR does not replace full-text document search for deep reading tasks.
- This ADR does not permit bypassing confirmation, policy, or role checks.

## Related ADRs

- ADR 0209: Use-case services and thin delivery adapters
- ADR 0235: Cross-application launcher and favorites
- ADR 0239: Browser-local search experience via Pagefind
- ADR 0243: Component stories, accessibility, and UI contracts
- ADR 0309: Task-oriented information architecture across the platform

## References

- <https://cmdk.paco.me>
- [Browser-Local Search Experience Via Pagefind](0239-browser-local-search-experience-via-pagefind.md)
