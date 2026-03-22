# ADR 0070: Retrieval-Augmented Context For Platform Queries

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Agents and operators querying this platform face a context assembly problem:

- the authoritative answer to most questions is spread across ADRs, runbooks, `stack.yaml`, receipts, and live metrics
- a conversational agent must either read all of these files on every query (slow, expensive, context-limited) or rely on stale in-context summaries that drift from reality
- there is no mechanism for an agent to quickly locate the most relevant 3-5 documents for a given operational question without scanning the entire repository

As the ADR count passes 70 and the runbook count passes 50, this retrieval problem compounds. An agent that cannot efficiently ground its answers in repo truth is not reliably useful for operational decisions.

## Decision

We will build a retrieval-augmented generation (RAG) index over the platform's authoritative documents and expose it as a governed query tool.

Corpus:

- all ADRs under `docs/adr/`
- all runbooks under `docs/runbooks/`
- `versions/stack.yaml` (current platform state)
- all receipts under `receipts/live-applies/` (structured evidence)
- `config/workflow-catalog.json`, `config/command-catalog.json`, `config/agent-tool-registry.json`
- changelog and VERSION

Index:

- documents are chunked, embedded, and stored in a private vector database (initial candidate: Qdrant in a Docker container on `docker-runtime-lv3`)
- the index is rebuilt on every merge to `main` via a Windmill workflow (`rebuild-rag-index`)
- each chunk retains its source file path, ADR number (if applicable), and last-modified date as metadata for citation

Query tool (`query-platform-context`):

- accepts a natural-language question
- returns the top-k most relevant chunks with source citations
- is listed in the agent tool registry (ADR 0069) under the `observe` category
- is accessible from Open WebUI (ADR 0060) as a built-in tool and from any MCP-compatible agent runtime

Access:

- the query endpoint is private-first (ADR 0049) and requires a valid internal credential
- no raw document contents are returned over public interfaces

## Consequences

- Agents can ground operational answers in current repo state without reading the full repository on every query.
- The index freshness is bounded by merge cadence; very recent changes may not yet be indexed.
- A vector database is another stateful service that must be operated, backed up, and recovered.
- Embedding costs are zero for a self-hosted model (e.g. a local embedding model on `docker-runtime-lv3`); no external API dependency is introduced.

## Boundaries

- The RAG index is read-only context retrieval; it does not make decisions or execute actions.
- Live metric data and real-time log streams are not indexed; they are accessed via dedicated observability tools.
- The index does not replace canonical file reads for automated scripts; it is optimised for conversational and exploratory queries.
