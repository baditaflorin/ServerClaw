# Workstream ADR 0198: Qdrant Vector Search for Semantic Platform RAG

- ADR: [ADR 0198](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0198-live-apply/docs/adr/0198-qdrant-vector-search-semantic-rag.md)
- Title: Semantic retrieval for platform RAG using Qdrant and local Ollama embeddings
- Status: merged
- Branch: `codex/ws-0198-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0198-live-apply`
- Owner: codex
- Depends On: `adr-0070-rag-context`, `adr-0145-private-ollama`, `adr-0167-agent-handoff-and-context-preservation`
- Conflicts With: none
- Shared Surfaces: `platform/llm/`, `scripts/platform_context_service.py`, `scripts/platform_context_corpus.py`, `scripts/query_platform_context.py`, `scripts/lv3_cli.py`, `roles/rag_context_runtime/`, `inventory/group_vars/all.yml`, `docs/runbooks/rag-platform-context.md`, `workstreams.yaml`

## Scope

- switch the platform-context runtime from token-hash embeddings to semantic embeddings backed by local Ollama
- ensure the `nomic-embed-text` model is present during the managed live apply
- expand the indexed corpus to include the canonical error-code and service/dependency catalogs
- expose semantic retrieval through `platform.llm.PlatformLLMClient.retrieve()` and `lv3 query-platform-context`
- preserve keyword fallback behavior when vector retrieval is unavailable
- record the live apply, verification evidence, and merge-safe follow-up notes

## Non-Goals

- public edge publication of Qdrant
- Dify deployment itself from ADR 0197
- protected integration-file updates on this workstream branch

## Expected Repo Surfaces

- `docs/adr/0198-qdrant-vector-search-semantic-rag.md`
- `docs/workstreams/adr-0198-qdrant-vector-search-semantic-rag.md`
- `docs/runbooks/rag-platform-context.md`
- `platform/llm/client.py`
- `platform/llm/retrieval.py`
- `scripts/index_platform_knowledge.py`
- `scripts/lv3_cli.py`
- `scripts/platform_context_corpus.py`
- `scripts/platform_context_service.py`
- `scripts/query_platform_context.py`
- `roles/rag_context_runtime/`
- `inventory/group_vars/all.yml`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` rebuilds the platform-context collection with semantic Ollama embeddings
- the live `/v1/context/query` endpoint reports `retrieval_backend: "vector"` during steady-state operation
- `lv3 query-platform-context` returns cited semantic matches through the private platform-context API

## Verification

- `python3 scripts/index_platform_knowledge.py --dry-run`
- `uv run --with pytest --with pyyaml --with httpx --with fastapi --with qdrant-client --with pyyaml python -m pytest tests/test_platform_context_corpus.py tests/test_platform_context_service.py tests/test_platform_llm_client.py tests/test_lv3_cli.py -q`
- `./scripts/validate_repo.sh data-models workstream-surfaces agent-standards`
- `make syntax-check-rag-context`
- `make live-apply-service service=rag-context env=production`

## Merge Criteria

- the live platform no longer reports `token-hash` as the active retrieval backend for platform-context queries
- semantic retrieval is verified end to end against the live Ollama-backed runtime
- `platform.llm.PlatformLLMClient` injects cited retrieval context before completion calls
- protected integration files are left unchanged on the workstream branch and called out explicitly for merge-to-main

## Outcome

- `make preflight WORKFLOW=converge-rag-context`, `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:rag-context`, and `make converge-rag-context` completed successfully from a worktree rooted at `origin/main` commit `e213cce2`.
- The managed converge pulled `nomic-embed-text:latest` into the local Ollama runtime on `docker-runtime-lv3`, rebuilt the platform-context corpus, and completed the live query verification with cited results.
- Post-apply operator verification through `PYTHONPATH=. uv run --with pyyaml python scripts/lv3_cli.py query-platform-context ... --json`, `PYTHONPATH=. uv run --with pyyaml python scripts/query_platform_context.py --question ...`, and a direct authenticated `curl` to `/v1/context/query` all returned `retrieval_backend: "vector"`.
- The live health probe returned `{"status":"ok","collection":"platform_context"}`, and the platform-context API logs recorded answered queries with `retrieval_backend":"vector"` after the rollout.
- The durable replay evidence is captured in `receipts/live-applies/2026-03-27-adr-0198-semantic-rag-live-apply.json`.

## Notes For The Next Assistant

- `make live-apply-service service=rag-context env=production` is still blocked on this branch by an unrelated stale canonical-truth check that wants to rewrite protected `README.md` content inherited from `origin/main`; do not resolve that on this workstream branch.
- Merge to `main` still needs the protected integration-file follow-up for `README.md`, `VERSION`, the release sections in `changelog.md`, and `versions/stack.yaml` once the semantic RAG rollout is integrated.
