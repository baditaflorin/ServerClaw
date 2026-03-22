# Workstream ADR 0070: Retrieval-Augmented Context For Platform Queries

- ADR: [ADR 0070](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0070-rag-context-for-platform-queries.md)
- Title: Vector-indexed platform corpus for grounded agent and operator queries
- Status: merged
- Branch: `codex/adr-0070-rag-platform-context`
- Worktree: `../proxmox_florin_server-rag-platform-context`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0049-private-api-publication`, `adr-0060-open-webui-workbench`, `adr-0069-agent-tool-registry`
- Conflicts With: none
- Shared Surfaces: `docs/`, `config/`, `versions/stack.yaml`, `receipts/`, Windmill workflows, Open WebUI

## Scope

- deploy Qdrant on `docker-runtime-lv3` as the vector database
- write `scripts/build_rag_index.py` to chunk, embed, and upload corpus documents
- create Windmill workflow `rebuild-rag-index` triggered on main merges
- expose `query-platform-context` as a tool in the agent tool registry (ADR 0069)
- integrate the query tool into Open WebUI as a built-in function
- document the corpus, chunking strategy, and update cadence in `docs/runbooks/rag-platform-context.md`

## Non-Goals

- live metric data or real-time log streams in the index
- external embedding API dependencies

## Expected Repo Surfaces

- `scripts/build_rag_index.py`
- Windmill workflow definition for index rebuild
- updated `config/agent-tool-registry.json` with `query-platform-context` tool
- `docs/runbooks/rag-platform-context.md`
- `docs/adr/0070-rag-context-for-platform-queries.md`
- `docs/workstreams/adr-0070-rag-platform-context.md`
- `workstreams.yaml`

## Expected Live Surfaces

- Qdrant running on `docker-runtime-lv3` with indexed platform corpus
- Windmill workflow scheduled to rebuild on merge
- `query-platform-context` callable from Open WebUI and MCP-compatible agents

## Verification

- Qdrant health endpoint returns 200
- `scripts/build_rag_index.py --dry-run` completes without error
- a test query for "how does step-ca issue SSH certificates" returns relevant ADR chunks with source citations

## Merge Criteria

- the embedding model runs locally with no external API calls
- the corpus is indexed and a test query produces grounded results
- source citations include file path and ADR number where applicable
- query access requires a valid internal credential

## Notes For The Next Assistant

- use a small local embedding model (e.g. `sentence-transformers/all-MiniLM-L6-v2` via `ollama` or direct HuggingFace) to avoid API costs
- chunk ADRs at the section level (H2 boundaries) to preserve context coherence

## Repo Implementation Notes

- Repo implementation completed on `2026-03-22` for release `0.62.0`.
- The repo now carries the `rag-context` playbook, `roles/rag_context_runtime`, the private platform-context API service code, Qdrant-backed runtime definitions, and the supporting runbook or tests.
- Live apply is still pending because this release commit does not by itself change the running platform.
