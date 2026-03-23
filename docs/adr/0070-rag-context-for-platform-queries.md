# ADR 0070: Retrieval-Augmented Context For Platform Queries

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.62.0
- Implemented In Platform Version: 0.35.0
- Implemented On: 2026-03-23
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

- documents are chunked and stored with citation metadata in a private vector database (Qdrant on `docker-runtime-lv3`)
- embedding is performed by a local model inside the private platform-context API runtime; no external embedding API is required
- the index can be rebuilt through the repo-managed script `scripts/build_rag_index.py` and the seeded Windmill script `rebuild_rag_index`
- each chunk retains its source file path, ADR number (if applicable), section heading, and last-modified timestamp as metadata for citation

Query tool (`query-platform-context`):

- accepts a natural-language question
- returns the top-k most relevant chunks with source citations
- is listed in the agent tool registry (ADR 0069) under the `observe` category
- is exposed through a private OpenAPI tool server so Open WebUI (ADR 0060) can register it as a global tool and MCP-compatible runtimes can load the registry export

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

## Implementation Notes

- The private runtime now converges through [playbooks/rag-context.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/rag-context.yml) and [roles/rag_context_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/rag_context_runtime) on `docker-runtime-lv3`.
- Qdrant and the FastAPI-based platform context API are deployed together, with a controller-local bearer token mirrored under `.local/platform-context/api-token.txt`.
- [scripts/platform_context_corpus.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/platform_context_corpus.py) defines corpus discovery and chunking, keeping ADRs and runbooks aligned to Markdown `##` boundaries before paragraph splitting.
- [scripts/build_rag_index.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/build_rag_index.py) now provides the canonical dry-run and upload path for corpus builds, and [scripts/query_platform_context.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/query_platform_context.py) provides a direct private query client.
- [scripts/platform_context_service.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/platform_context_service.py) serves the private OpenAPI tool surface for `query-platform-context`, workflow or command contract lookups, recent receipt reporting, and platform summary reads.
- Operator usage and Open WebUI global-tool integration are documented in [docs/runbooks/rag-platform-context.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/rag-platform-context.md).
