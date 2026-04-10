# ADR 0377: Open WebUI Platform Knowledge Integration

- Status: Deprecated
- Implementation Status: Not Implemented
- Date: 2026-04-06

## Context

Open WebUI at `chat.lv3.org` currently runs Llama 3.2 3B with no platform
context. Users asking about the LV3 platform, available services, agent tools,
or operational procedures get generic chatbot answers because the model has
no knowledge of the environment it is deployed in.

Meanwhile, the platform already maintains rich structured knowledge:

- **Platform context corpus** (`scripts/platform_context_corpus.py`) indexing
  ADRs, runbooks, command contracts, service catalogs, and error registries
- **Qdrant vector database** (ADR 0198) with `platform_context` collection
  using `nomic-embed-text` embeddings via local Ollama
- **ServerClaw memory substrate** (ADR 0263) with structured memory objects
  in PostgreSQL and semantic recall in Qdrant
- **Repowise semantic search** (ADR 0346) for code-level queries
- **Agent tool registry** (`config/agent-tool-registry.json`) with 32
  governed tools across observe, execute, and approve categories
- **Skill packs** (ADR 0257) with bundled, shared, and workspace-scoped
  SKILL.md definitions
- **SearXNG** already wired for web search but not for platform-internal
  search

The gap is straightforward: none of this knowledge reaches the chat frontend.

## Decision

We will wire platform knowledge into Open WebUI through three layers:

### Layer 1: RAG Knowledge Base via Qdrant

Open WebUI supports external RAG backends. We will configure it to use the
existing Qdrant `platform_context` collection as a knowledge source.

**Implementation:**

1. Enable Open WebUI's RAG integration and point it at the Qdrant instance
   on `docker-runtime-lv3`
2. Configure the embedding model to use the same `nomic-embed-text` model
   via the local Ollama endpoint (ensuring vector compatibility)
3. Set the RAG collection to `platform_context` so queries hit the same
   corpus that `query-platform-context` uses
4. Configure chunk retrieval count (k=5) and similarity threshold to match
   existing `platform.llm.PlatformLLMClient.retrieve()` behavior

**What this gives the chatbot:** Automatic retrieval of relevant ADRs,
runbooks, service documentation, and operational procedures when users ask
questions about the platform.

### Layer 2: System Prompt with Platform Identity

Create a platform-aware system prompt that:

1. Identifies the chatbot as the LV3 platform assistant (ServerClaw)
2. Summarizes the platform topology (hosts, services, URLs)
3. Lists available agent tool categories and how to request actions
4. References the skill pack catalog for capability discovery
5. Directs users to specific runbooks or ADRs when relevant

**Implementation:**

1. Create a Jinja2 template for the system prompt at
   `roles/open_webui_runtime/templates/system-prompt.md.j2`
2. Populate it from `config/agent-tool-registry.json` (tool names and
   descriptions), `config/serverclaw/skill-packs.yaml` (available skills),
   and `config/service-topology.yaml` (service URLs)
3. Inject the system prompt via Open WebUI's `DEFAULT_SYSTEM_PROMPT`
   environment variable or model configuration

### Layer 3: Indexed Knowledge Documents

For structured reference material that benefits from exact retrieval rather
than semantic similarity:

1. Auto-generate a **service catalog document** listing all deployed services,
   their URLs, purpose, and current status
2. Auto-generate a **tool catalog document** listing all 32 governed tools
   with their descriptions, categories, and invocation patterns
3. Auto-generate a **skill catalog document** from `skill-packs.yaml`
4. Upload these as Open WebUI knowledge base documents via the admin API
   during convergence

These documents will be regenerated on each deployment to stay current.

### Corpus Freshness

The platform context corpus must be re-indexed when structural changes occur
(new services, new ADRs, new tools). This is already handled by
`scripts/index_platform_knowledge.py`. We will add a post-convergence hook
to the Open WebUI role that triggers re-indexing when knowledge-affecting
files change.

## Consequences

### Positive

- Users chatting at `chat.lv3.org` get answers grounded in actual platform
  documentation instead of hallucinated generic responses
- No new infrastructure required — reuses existing Qdrant, Ollama, and
  platform context corpus
- Knowledge stays fresh through convergence-time regeneration
- System prompt provides immediate context without waiting for RAG retrieval

### Negative

- Llama 3.2 3B may not be capable enough to effectively use RAG context —
  if retrieval quality is poor, upgrading the model (e.g., to Llama 3.1 8B
  or Qwen 2.5 7B) may be required as a follow-up
- System prompt size is limited; must be kept concise while still useful
- Knowledge document generation adds convergence time (mitigated by only
  regenerating on structural changes)

### Risks

- Stale RAG index could provide outdated answers — mitigated by
  convergence-time re-indexing
- Model may confidently present retrieved context incorrectly — mitigated
  by including source references in retrieval results

## Dependencies

- ADR 0198 (Qdrant vector search) — must be deployed and indexed
- ADR 0145 (Ollama runtime) — embedding model must be available
- ADR 0060 (Open WebUI) — the target integration surface
- ADR 0254 (ServerClaw) — identity and product framing
