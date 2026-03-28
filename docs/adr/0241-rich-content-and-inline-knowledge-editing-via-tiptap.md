# ADR 0241: Rich Content And Inline Knowledge Editing Via Tiptap

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not yet (pending main merge)
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

Human users need to create and update structured written content inside the
platform:

- inline handoff notes
- incident timelines
- rich comments on tasks or automation runs
- bounded knowledge blocks attached to services or runbooks

Plain textareas are too limiting, while hand-built rich-text editors are
notoriously brittle.

## Decision

We will use **Tiptap** as the default rich-content editor framework for
first-party inline and bounded knowledge-editing surfaces.

### Approved content capabilities

- headings, lists, links, code blocks, tables, and task items
- mention-style references to services, runbooks, or people when the page owns
  that concept
- markdown import and export where the surrounding workflow benefits from it

### Role split

- Outline remains the long-form living knowledge system of record
- Tiptap is the editor framework for rich inputs inside other first-party apps

## Consequences

**Positive**

- rich inputs become more usable without building a custom editor from scratch
- the platform can share one extensible editing model across several surfaces
- content capabilities can grow by enabling extensions rather than rewriting the
  editor foundation

**Negative / Trade-offs**

- rich content adds content-model and sanitization responsibilities
- migration from plain text or legacy HTML requires care

## Boundaries

- This ADR does not replace Outline for wiki-scale authoring.
- Arbitrary raw HTML is not an approved content model for first-party editors.

## Related ADRs

- ADR 0131: Multi-agent handoffs
- ADR 0199: Outline living knowledge wiki
- ADR 0209: Use-case services and thin delivery adapters

## References

- <https://tiptap.dev/docs/editor/getting-started/overview>
