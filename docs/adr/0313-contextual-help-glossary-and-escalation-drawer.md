# ADR 0313: Contextual Help, Glossary, And Escalation Drawer

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-31

## Context

The repository already contains strong documentation and runbooks, but users
still have to leave the flow of work to answer basic questions:

- what does this page do?
- what does this platform term mean?
- where is the right runbook?
- what should I do if this action fails or I get stuck?

That context switch is especially painful during onboarding, incidents, and
infrequently used administrative tasks.

## Decision

We will provide a shared **contextual help and escalation drawer** in
first-party browser surfaces.

### Drawer contents

Every first-party page should be able to surface:

- a short explanation of the page purpose and intended audience
- glossary definitions for platform-specific terms on that page
- links to the most relevant runbooks, ADRs, and reference pages
- the escalation path if the user cannot proceed safely

### Content-source rule

The help drawer should not become a second documentation system. It should
summarize and deep-link to the canonical sources already maintained in docs,
runbooks, and living knowledge surfaces.

### Escalation rule

When a page includes a risky or failure-prone task, the help drawer must say:

- how to back out safely
- where to find the owning runbook
- how to ask for help or hand off the task

## Consequences

**Positive**

- users can answer common questions without abandoning their current page
- platform vocabulary becomes more consistent because the glossary is visible in
  context
- the help system becomes a practical bridge between onboarding, docs, and
  operational recovery

**Negative / Trade-offs**

- context-aware help content must stay synchronized with the page behavior or it
  becomes misleading
- the drawer can become cluttered if it tries to mirror full documentation

## Boundaries

- This ADR does not replace full runbooks, docs, or wiki content.
- This ADR does not require third-party product-native UIs to expose the same
  drawer, though the workbench should still link to contextual help before the
  user leaves a first-party page.

## Related ADRs

- ADR 0094: Developer portal and documentation site
- ADR 0199: Outline living knowledge wiki
- ADR 0239: Browser-local search experience via Pagefind
- ADR 0242: Guided human onboarding via Shepherd tours
- ADR 0312: Shared notification center and activity timeline

## References

- [Developer Portal](../runbooks/developer-portal.md)
- [Portal Authentication By Default](../runbooks/portal-authentication-by-default.md)
