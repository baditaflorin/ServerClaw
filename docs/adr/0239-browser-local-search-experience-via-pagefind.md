# ADR 0239: Browser-Local Search Experience Via Pagefind

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.62
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

The platform already has repository-local and API-backed search under ADR 0121,
but human UX still needs a fast, browser-friendly way to search documentation,
runbooks, ADRs, changelog pages, and other generated content without waiting on
a live backend round-trip for every keystroke.

That matters during onboarding, routine operations, and degraded-network
conditions.

## Decision

We will use **Pagefind** as the default browser-local search layer for static or
semi-static human-readable surfaces.

### Expected usage

- build search indexes during docs and portal publication
- expose facets for capability, service, audience, and sensitivity where the
  corpus supports them
- use Pagefind UI or a thin integration in the shared app shell rather than
  building custom client-side search from scratch

### Relationship to existing search

- Pagefind complements ADR 0121 instead of replacing it
- browser-local search is preferred for published content corpora
- API search remains the path for live structured data and richer runtime
  queries

## Consequences

**Positive**

- users get fast search for docs-like content with no live backend dependency
- search UX can stay available during partial control-plane degradation
- repo publication remains the canonical moment where search indexes are
  generated

**Negative / Trade-offs**

- search freshness depends on the publication pipeline
- Pagefind is best for published corpora, not live operational records

## Boundaries

- This ADR is not a replacement for API-backed runtime search.
- Sensitive content still follows the publication and redaction rules already
  established elsewhere.

## Related ADRs

- ADR 0094: Developer portal and documentation site
- ADR 0121: Local search and indexing fabric
- ADR 0134: Changelog portal content redaction
- ADR 0199: Outline living knowledge wiki

## References

- <https://pagefind.app/docs/>
