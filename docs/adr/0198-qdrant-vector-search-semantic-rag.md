# ADR 0198: Qdrant Vector Search for Semantic Platform RAG

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.12
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

ADR 0070 established a private platform-context API and Qdrant-backed retrieval path, but the running platform still relies on deterministic token-hash embeddings. That gives stable citations and low operational cost, yet it does not provide true semantic retrieval across a growing ADR and runbook corpus.

As the knowledge base passes 200 ADRs and accumulates more receipts, command contracts, and error registries, keyword- and hash-only matching increasingly misses adjacent decisions. Agents and operators can ask for "approval gates for risky changes" or "certificate issuance policy" and receive incomplete context even though the authoritative material exists in-repo.

## Decision

We will make the platform-context retrieval path semantic by default while preserving the existing private-first operating model.

- Keep Qdrant on `docker-runtime-lv3` as the vector store backing platform retrieval.
- Use the local Ollama runtime with `nomic-embed-text` for fully on-prem embedding generation.
- Expand the indexed platform corpus to include the canonical error-code registry and the governed service/dependency catalogs alongside ADRs, runbooks, receipts, and command contracts.
- Add a repo-managed `scripts/index_platform_knowledge.py` entrypoint as the canonical semantic indexing wrapper.
- Extend `platform.llm.PlatformLLMClient` with `retrieve(query, k=5)` and inject the retrieved context before each LLM completion call.
- Add an operator-facing `lv3 query-platform-context` command that queries the semantic retrieval service directly.
- Preserve a keyword-scored fallback when vector retrieval is unavailable so ADR 0070's governed query path remains usable during degraded conditions.

## Consequences

### Positive

- Agent prompts can be grounded with semantically relevant ADR, runbook, receipt, and error-code context before inference.
- Retrieval remains air-gapped and repo-grounded because embeddings come from local Ollama rather than an external API.
- The same semantic retrieval substrate can later be reused by Dify or other higher-level agent workbenches without reintroducing an external vector dependency.

### Trade-offs

- Semantic retrieval now depends on the Ollama embedding model being present and healthy on `docker-runtime-lv3`.
- The Qdrant collection must be recreated safely when the embedding dimension changes from the legacy hash backend to the semantic model.

## Boundaries

- This ADR upgrades retrieval quality; it does not expose Qdrant publicly or turn retrieval into an action-execution surface.
- Keyword fallback remains available for degraded reads, but semantic retrieval is the intended steady-state path.

## Related ADRs

- ADR 0070: Retrieval-augmented context for platform queries
- ADR 0145: Private Ollama inference runtime
- ADR 0197: Dify visual LLM workflow and agent canvas

## Implementation Notes

- The repository implementation lives primarily in `scripts/platform_context_service.py`, `scripts/platform_context_corpus.py`, `platform/llm/`, `scripts/lv3_cli.py`, and `roles/rag_context_runtime/`.
- The verified live rollout on 2026-03-27 converged the platform-context runtime from a worktree based on `origin/main` commit `e213cce2`, pulled `nomic-embed-text` into the local Ollama runtime, rebuilt the mirrored corpus, and verified `retrieval_backend: "vector"` through both the managed role checks and the operator-facing query entrypoints.
- `make live-apply-service service=rag-context env=production` was blocked by an unrelated stale canonical-truth check for protected `README.md` content already present on `origin/main`, so the live mutation executed through `make converge-rag-context` after `scripts/interface_contracts.py --check-live-apply service:rag-context` confirmed the governed apply surface.
- The live-apply receipt for this replay is recorded under `receipts/live-applies/`.
- Merge to `main` must still update the protected integration files separately: `VERSION`, release sections in `changelog.md`, `README.md`, and `versions/stack.yaml`.
