# ADR 0346 — Repowise: local semantic code search over the git repo

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.125
- Implemented In Platform Version: 0.178.77
- Implemented On: 2026-04-12
- Date: 2026-04-05

## Context

The platform repository has grown to 2,600+ files across Ansible roles, Python scripts, ADRs, and runbooks. Operators and agents need to locate relevant code, roles, and documentation by semantic meaning rather than exact filename or string match.

Third-party embedding APIs (Voyage AI, OpenAI, Anthropic) introduce external dependencies and potential data exposure. The platform already runs Ollama and Qdrant on `docker-runtime`.

## Decision

Deploy repowise — a local semantic code search service — using:

- **Corpus builder** (`repowise_corpus.py`): language-aware chunking (Python by function/class, Ansible YAML by task block, Markdown by H2 section, generic by paragraph overlap). Produces ~19k chunks from ~2,625 files.
- **Indexer** (`repowise_index.py`): embeds chunks via Ollama `nomic-embed-text` (768 dimensions, CPU-only), stores in Qdrant `repowise` collection.
- **FastAPI service** (`repowise_service.py`): `/search` endpoint with `language` and `document_kind` filters, optional bearer token auth, async rebuild endpoint.
- **Ansible role** `repowise_runtime`: deploys on `docker-runtime`, joins `platform-context_default` Docker network to reach existing Qdrant, schedules nightly index rebuild via cron.

No third-party APIs are used.

## Consequences

- Semantic search available at `http://docker-runtime:7070/search` (internal only until nginx edge is published).
- Nightly cron rebuild at 03:00 keeps the index current with `main`.
- Adding new files or roles is automatically picked up on the next rebuild.
