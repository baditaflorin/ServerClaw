# ADR 0145: Ollama for Local LLM Inference API

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform's agentic components (Open WebUI, ADR 0060; the goal compiler, ADR 0112; interactive Claude Code sessions) currently use external LLM APIs (Anthropic Claude, OpenAI) for language model inference. This creates:

- **Privacy exposure**: every prompt sent to an external API reveals platform state, infrastructure details, and operational context to the API provider.
- **External availability dependency**: if the API is unavailable or rate-limited, agent workflows that depend on LLM inference are blocked.
- **Per-token cost**: for high-frequency agentic tasks (triage context summarisation, runbook step description generation, goal compilation edge cases) the per-token cost adds up.
- **Latency**: round-trip to an external API adds 200–2000ms per inference call, which is significant for multi-step agentic workflows.

**Ollama** is an open-source local LLM inference server that provides an OpenAI-compatible REST API for locally-hosted models (Llama 3, Mistral, Qwen, Gemma, etc.). It runs efficiently on CPU for small and medium models, making it practical on a single Proxmox node without a GPU.

For tasks that do not require frontier model capability — structured data extraction, intent normalisation for the goal compiler, triage signal description, runbook step summarisation — a smaller local model (7B–13B parameters, quantised) is sufficient and preferable to an external API call on privacy, latency, and cost grounds.

The platform principle is: use the smallest, most local model that is sufficient for the task. Reserve external frontier models (Claude, GPT-4) for tasks that genuinely require their capability.

## Decision

We will deploy **Ollama** on the `docker-runtime-lv3` VM as a Docker Compose service, providing a local OpenAI-compatible inference API accessible to all platform agents.

### Deployment

```yaml
# In versions/stack.yaml — new service entry
- service: ollama
  vm: docker-runtime-lv3
  image: ollama/ollama:latest
  port: 11434
  access: internal_only    # No public access; Tailscale-only
  data_volume: /data/ollama/models
  resource_limits:
    memory: 8Gi            # Model weights live in RAM; constrain to avoid OOM on other services
    cpu: 4
```

### Model catalog

Models are managed declaratively in `config/ollama-models.yaml`:

```yaml
# config/ollama-models.yaml

models:
  - name: llama3.2:3b-instruct-q8_0
    use_cases: [goal_compiler_normalisation, triage_signal_description]
    max_context: 4096
    ram_requirement_gb: 4
    pull_on_startup: true

  - name: mistral:7b-instruct-q4_K_M
    use_cases: [runbook_step_summarisation, search_query_expansion]
    max_context: 8192
    ram_requirement_gb: 5
    pull_on_startup: true

  - name: qwen2.5:7b-instruct
    use_cases: [structured_extraction, json_generation]
    max_context: 8192
    ram_requirement_gb: 6
    pull_on_startup: false   # Pulled on first use; not always needed
```

A Windmill workflow `ollama-model-sync` runs on startup and weekly to ensure declared models are pulled and available. Model files are stored in `/data/ollama/models` on a volume backed by the PBS backup policy.

### Platform LLM client

A thin wrapper `platform/llm/client.py` abstracts over local (Ollama) and external (Anthropic) models with a routing policy:

```python
# platform/llm/client.py

class PlatformLLMClient:
    def complete(self, prompt: str, use_case: str, max_tokens: int = 512) -> str:
        model = self._route(use_case)
        if model.provider == "ollama":
            return self._ollama_complete(prompt, model.name, max_tokens)
        elif model.provider == "anthropic":
            return self._anthropic_complete(prompt, model.name, max_tokens)

    def _route(self, use_case: str) -> Model:
        # Use local Ollama model for declared use cases
        for m in self.model_catalog:
            if use_case in m.use_cases:
                if self._ollama_available() and self._model_available(m.name):
                    return Model(provider="ollama", name=m.name)
        # Fallback to external API only if local model unavailable
        return Model(provider="anthropic", name="claude-haiku-4-5")
```

The routing policy is deterministic and observable: every LLM call records `provider`, `model`, `use_case`, `prompt_tokens`, `completion_tokens`, and `latency_ms` to the mutation ledger (ADR 0115) under `event_type: llm.inference`.

### Goal compiler integration

The goal compiler (ADR 0112) currently uses deterministic rule matching for intent normalisation. For instructions that do not match any rule (the fallback path), the goal compiler optionally calls Ollama with a structured prompt to normalise the instruction before declaring it unknown:

```python
# In goal_compiler/compiler.py — fallback path
if not rule_match:
    normalised = llm.complete(
        prompt=f"Normalise this platform instruction to canonical form: '{instruction}'",
        use_case="goal_compiler_normalisation",
        max_tokens=64,
    )
    rule_match = self._match_rule(normalised)
```

This is a bounded, low-stakes use of local inference: it improves natural-language flexibility without exposing the platform to an external API for normalisation tasks.

### Open WebUI integration

The existing Open WebUI deployment (ADR 0060) is connected to the local Ollama instance as an additional model source, alongside the existing external API connections:

```yaml
# Open WebUI environment: OLLAMA_BASE_URL points to local Ollama
OLLAMA_BASE_URL: "http://ollama:11434"
```

Operators can now run queries against local models for platform-related questions without any external API calls.

## Consequences

**Positive**

- Platform-related LLM queries (triage context summarisation, runbook interpretation, instruction normalisation) never leave the private network. Infrastructure details do not reach external API providers.
- Local inference latency for small models is 100–500ms on CPU, comparable to or faster than external API round-trips for short completions.
- The fallback routing means external API calls continue to work when the local model is unavailable or insufficient for the task.
- Open WebUI gains local model options, reducing API costs for interactive operator queries.

**Negative / Trade-offs**

- Running a 7B model at 4-bit quantisation requires ~5 GB of RAM. On a Proxmox host with other VMs, this is significant. If memory pressure is a problem, model loading/unloading overhead adds latency to the first inference call after an idle period.
- Local models (7B-13B parameters) are less capable than frontier models for complex reasoning tasks. The routing policy must be conservative: do not route tasks to local models where a wrong answer causes a real operation to fail.
- Model files are large (3–6 GB each). Storing them on PBS backup adds to the backup size. A retention policy for model files should be separate from operational data.

## Boundaries

- Ollama handles inference only. It does not store conversation history; that remains in Open WebUI or the agent state store (ADR 0130).
- External frontier model API keys (Anthropic, OpenAI) remain in OpenBao for tasks that require them. Ollama does not replace them; it supplements them.
- This ADR does not govern which tasks use LLM inference at all; that is decided by each component's ADR (goal compiler, triage engine, etc.).

## Related ADRs

- ADR 0043: OpenBao (external API key storage)
- ADR 0044: Windmill (model sync workflow)
- ADR 0060: Open WebUI (Ollama as additional model source)
- ADR 0112: Deterministic goal compiler (local LLM for normalisation fallback)
- ADR 0115: Event-sourced mutation ledger (llm.inference events)
- ADR 0146: Langfuse (observability for all LLM calls including Ollama)
