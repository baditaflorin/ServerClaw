# Workstream ADR 0198: Qdrant Vector Search for Semantic Platform RAG

- ADR: [ADR 0198](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0198-main-final/docs/adr/0198-qdrant-vector-search-semantic-rag.md)
- Title: Semantic retrieval for platform RAG using Qdrant and local Ollama embeddings
- Status: ready
- Branch: `codex/ws-0198-main-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0198-main-final`
- Owner: codex
- Depends On: `adr-0070-rag-context`, `adr-0145-private-ollama`, `adr-0167-agent-handoff-and-context-preservation`
- Conflicts With: none
- Shared Surfaces: `platform/llm/`, `scripts/build_rag_index.py`, `scripts/platform_context_service.py`, `scripts/platform_context_corpus.py`, `scripts/query_platform_context.py`, `scripts/lv3_cli.py`, `roles/rag_context_runtime/`, `config/ansible-execution-scopes.yaml`, `scripts/service_id_resolver.py`, `scripts/standby_capacity.py`, `scripts/service_redundancy.py`, `scripts/immutable_guest_replacement.py`, `docs/runbooks/rag-platform-context.md`, `workstreams.yaml`

## Scope

- switch the platform-context runtime from token-hash embeddings to semantic embeddings backed by local Ollama
- ensure the `nomic-embed-text` model is present during the managed live apply
- expand the indexed corpus to include the canonical error-code and service/dependency catalogs
- expose semantic retrieval through `platform.llm.PlatformLLMClient.retrieve()` and `lv3 query-platform-context`
- preserve keyword fallback behavior when vector retrieval is unavailable
- repair degraded vector collections during governed live apply without forcing a synchronous full corpus rebuild on `docker-runtime-lv3`
- record the live apply, verification evidence, and merge-safe follow-up notes

## Non-Goals

- public edge publication of Qdrant
- Dify deployment itself from ADR 0197
- protected integration-file updates on this workstream branch

## Expected Repo Surfaces

- `docs/adr/0198-qdrant-vector-search-semantic-rag.md`
- `docs/workstreams/adr-0198-qdrant-vector-search-semantic-rag.md`
- `docs/runbooks/rag-platform-context.md`
- `config/ansible-execution-scopes.yaml`
- `platform/llm/client.py`
- `platform/llm/retrieval.py`
- `scripts/build_rag_index.py`
- `scripts/index_platform_knowledge.py`
- `scripts/lv3_cli.py`
- `scripts/platform_context_corpus.py`
- `scripts/platform_context_service.py`
- `scripts/query_platform_context.py`
- `scripts/service_id_resolver.py`
- `scripts/standby_capacity.py`
- `scripts/service_redundancy.py`
- `scripts/immutable_guest_replacement.py`
- `roles/rag_context_runtime/`
- `collections/ansible_collections/lv3/platform/roles/rag_context_runtime/`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` serves vector retrieval from a semantic Ollama-backed collection and repairs legacy dimension drift during managed live apply
- the live `/v1/context/query` endpoint reports `retrieval_backend: "vector"` during steady-state operation
- `lv3 query-platform-context` returns cited semantic matches through the private platform-context API

## Verification

- `python3 scripts/index_platform_knowledge.py --dry-run`
- `uv run --with pytest --with pyyaml --with httpx --with fastapi --with qdrant-client --with pyyaml python -m pytest tests/test_platform_context_corpus.py tests/test_platform_context_service.py tests/test_platform_llm_client.py tests/test_lv3_cli.py -q`
- `./scripts/validate_repo.sh data-models workstream-surfaces agent-standards`
- `make syntax-check-rag-context`
- `make live-apply-service service=rag-context env=production`
- `uv run --with pyyaml python3 scripts/live_apply_receipts.py --validate`

## Merge Criteria

- the live platform no longer reports `token-hash` as the active retrieval backend for platform-context queries
- semantic retrieval is verified end to end against the live Ollama-backed runtime
- `platform.llm.PlatformLLMClient` injects cited retrieval context before completion calls
- the governed live-apply path self-heals legacy vector-dimension drift without forcing a synchronous full mirrored-corpus rebuild
- protected integration files are left unchanged on the workstream branch and called out explicitly for merge-to-main

## Outcome

- The first semantic live rollout on 2026-03-27 converged from `origin/main` commit `e213cce2`, pulled `nomic-embed-text:latest`, rebuilt the mirrored corpus, and verified `retrieval_backend: "vector"` through the managed converge plus the operator query entrypoints.
- The synchronized latest-main replay on 2026-03-28 ran from `origin/main` commit `b2756a4f` through `make live-apply-service service=rag-context env=production`, completed with `docker-runtime-lv3 : ok=96 changed=3 unreachable=0 failed=0 skipped=16` and `proxmox_florin : ok=36 changed=4 unreachable=0 failed=0 skipped=14`, and repaired a degraded legacy `384`-dimension collection with a bounded controller-side semantic seed rebuild before the final vector assertion.
- Post-apply operator verification through `PYTHONPATH=. uv run --with pyyaml python scripts/lv3_cli.py query-platform-context 'What retrieval backend is active for platform context?' --json`, `PYTHONPATH=. uv run --with pyyaml python scripts/query_platform_context.py --question 'What retrieval backend is active for platform context?'`, and an authenticated direct POST to `/v1/context/query` all returned `retrieval_backend: "vector"` with ADR 0198 as the top cited match.
- The live health probe returned `{"status":"ok","collection":"platform_context"}` after the replay, and the managed verify path now preserves a healthy vector collection when possible while leaving the full repo-grounded rebuild as a separate maintenance action.
- Durable replay evidence is captured in `receipts/live-applies/2026-03-27-adr-0198-semantic-rag-live-apply.json` and `receipts/live-applies/2026-03-28-adr-0198-semantic-rag-mainline-live-apply.json`.

## Notes For The Next Assistant

- Production live apply now succeeds on the latest-main replay path, but a full repo-grounded rebuild still belongs to an explicit maintenance action because the expanded mirrored corpus exceeds the safe synchronous Ollama budget on `docker-runtime-lv3`.
- Merge to `main` still needs the protected integration-file follow-up for `README.md`, `VERSION`, the release sections in `changelog.md`, and `versions/stack.yaml` once the semantic RAG rollout is integrated.
