# ADR 0263: Qdrant, PostgreSQL, And Local Search As The ServerClaw Memory Substrate

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.90
- Implemented In Platform Version: 0.130.60
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

The repository already has:

- PostgreSQL-backed structured state
- Qdrant-backed semantic retrieval
- a local search fabric for exact and keyword lookup
- Langfuse for traces and evaluation evidence

What it still does not have is a ServerClaw-specific memory contract that
combines those surfaces into one user-scoped assistant memory model.

Without that contract, “memory” risks becoming an ambiguous mix of:

- raw chat history
- vectorized recall
- observability traces
- connector payload caches

## Decision

We will use **PostgreSQL, Qdrant, and the local search fabric together** as the
ServerClaw memory substrate.

### Memory split

- PostgreSQL stores canonical structured state such as messages, reminders,
  entities, preferences, tasks, and provenance metadata
- Qdrant stores semantic recall for conversation summaries, imported documents,
  notes, and other embedding-backed memory objects
- local search provides exact and keyword recall across assistant-owned and
  platform-owned corpora where semantic search alone is insufficient

### Governance rule

Every durable memory object must carry:

- owner or workspace scope
- provenance
- retention or TTL class
- consent or delegation boundary where applicable
- last-refresh timestamp

### Non-memory rule

Langfuse remains the observability and evaluation record, not the canonical
assistant memory store.

## Consequences

**Positive**

- ServerClaw gets one layered memory model instead of several competing
  half-models.
- Structured recall, semantic recall, and exact recall each keep the job they
  are best at.
- Existing repo investments in Qdrant and local search become directly reusable
  for the product.

**Negative / Trade-offs**

- Memory governance becomes more explicit and therefore more work to model
  correctly.
- Keeping search indexes and vector collections fresh adds operational
  background work.

## Boundaries

- This ADR does not authorize indefinite retention of raw user conversations.
- Vector recall does not replace exact search or structured state.
- Platform documentation retrieval and user memory must remain scope-separated
  even if they reuse common substrate components.

## Related ADRs

- ADR 0121: Local search and indexing fabric
- ADR 0146: Langfuse for agent observability
- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3

## References

- <https://qdrant.tech/documentation/>
