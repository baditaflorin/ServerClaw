# ADR 0356: LLM Inference Routing and Model Registry

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: llm, ollama, open-webui, ai, token-budget, inference, agent-coordination

## Context

The platform runs multiple LLM-backed agents and human-facing tools:
- Claude Code agents (apply, config-diff, secret-rotation, review roles).
- n8n automation workflows that call LLM APIs for content processing.
- Dify pipelines for RAG and document workflows.
- Open WebUI for operator-facing chat with local models.
- Custom scripts that invoke Ollama directly for low-latency local inference.

Currently there is no canonical declaration of:
1. **Which model** each agent role or tool should use.
2. **Which inference backend** (local Ollama vs. remote API vs. Dify pipeline)
   routes requests for a given task type.
3. **What context window** the model has — critical for token budget enforcement
   (ADR 0352).
4. **What token spend limits** apply to a given agent role or automation.
5. **How fallback routing works** when the primary backend is unavailable.

The result: agents choose their own model, n8n workflows hardcode API endpoints,
and token spend is unmonitored. Local Ollama inference is underutilized for
tasks that do not require frontier model capabilities.

## Decision

### 1. Model registry

`config/llm-model-registry.yaml` declares all permitted models and their properties:

```yaml
schema_version: 1
models:
  claude-sonnet-4-6:
    provider: anthropic-api
    context_window_tokens: 200000
    cost_tier: high
    capabilities: [code, reasoning, tool-use, long-context]
    endpoint_env_var: ANTHROPIC_API_KEY

  claude-haiku-4-5:
    provider: anthropic-api
    context_window_tokens: 200000
    cost_tier: low
    capabilities: [code, fast-response, tool-use]
    endpoint_env_var: ANTHROPIC_API_KEY

  llama3.2:3b:
    provider: ollama
    context_window_tokens: 128000
    cost_tier: free
    capabilities: [summarization, classification, short-code]
    endpoint_url: "http://10.10.10.{{ ollama_vmid }}:11434"

  qwen2.5-coder:7b:
    provider: ollama
    context_window_tokens: 128000
    cost_tier: free
    capabilities: [code, diff-review]
    endpoint_url: "http://10.10.10.{{ ollama_vmid }}:11434"

  mistral-nemo:12b:
    provider: ollama
    context_window_tokens: 128000
    cost_tier: free
    capabilities: [reasoning, summarization, tool-use]
    endpoint_url: "http://10.10.10.{{ ollama_vmid }}:11434"
```

### 2. Agent role → model routing table

`config/llm-routing.yaml` maps each agent role and task type to a model:

```yaml
schema_version: 1
routes:
  # Agent roles
  apply-agent:
    primary: claude-sonnet-4-6
    fallback: mistral-nemo:12b
    max_tokens_per_session: 50000
    onboarding_pack_category: micro   # enforces ADR 0352

  config-diff-agent:
    primary: qwen2.5-coder:7b         # local, free, code-capable
    fallback: claude-haiku-4-5
    max_tokens_per_session: 10000
    onboarding_pack_category: nano

  secret-rotation-agent:
    primary: claude-haiku-4-5
    fallback: mistral-nemo:12b
    max_tokens_per_session: 5000
    onboarding_pack_category: nano

  monitor-agent:
    primary: llama3.2:3b              # local, fast, low-cost status checks
    fallback: claude-haiku-4-5
    max_tokens_per_session: 3000
    onboarding_pack_category: nano

  review-agent:
    primary: claude-sonnet-4-6
    fallback: qwen2.5-coder:7b
    max_tokens_per_session: 30000
    onboarding_pack_category: standard

  # n8n workflow task types
  n8n-summarize:
    primary: llama3.2:3b
    fallback: claude-haiku-4-5
    max_tokens_per_call: 2000

  n8n-classify:
    primary: llama3.2:3b
    fallback: claude-haiku-4-5
    max_tokens_per_call: 500

  n8n-extract:
    primary: qwen2.5-coder:7b
    fallback: claude-haiku-4-5
    max_tokens_per_call: 4000

  # Dify pipeline tasks
  dify-rag-query:
    primary: mistral-nemo:12b
    fallback: claude-haiku-4-5
    max_tokens_per_call: 8000

  dify-document-summary:
    primary: llama3.2:3b
    fallback: claude-haiku-4-5
    max_tokens_per_call: 3000
```

### 3. Routing resolution

`scripts/llm_router.py` (new):

```
llm_router.py resolve --role apply-agent        # returns model + endpoint JSON
llm_router.py resolve --role n8n-summarize      # returns model + endpoint JSON
llm_router.py health                             # check all registered endpoints
llm_router.py budget --role apply-agent --used 12000  # check remaining budget
```

Resolution algorithm:

1. Look up `primary` model for the given role in `llm-routing.yaml`.
2. Check if the model's endpoint is healthy (`/api/health` for Ollama,
   `/v1/models` for Anthropic-compatible).
3. If primary is unhealthy: use `fallback`.
4. If both unhealthy: exit 1 with `{"status": "error", "reason": "no_healthy_backend"}`.
5. Return endpoint URL, model ID, and `max_tokens` as JSON.

### 4. Token spend tracking

Each agent session declares `max_tokens_per_session` from its routing config.
The capability manifest (ADR 0349) includes `token_budget_remaining` updated
on each LLM call via `llm_router.py budget --decrement <n>`.

When `token_budget_remaining` reaches 0:
- The agent must not make further LLM calls.
- It must emit a `{"status": "budget_exhausted"}` event and either:
  a. Complete the task with non-LLM steps (Ansible apply, idempotent tool calls).
  b. Request a budget extension via the workstream (human approval required).

Token spend events are emitted to the mutation audit log (ADR 0354) with
`mutation.type: "llm_inference"`.

### 5. Ollama model provisioning

The `ollama_runtime` role is updated to declare which models are pulled on
deploy, sourced from `config/llm-model-registry.yaml`:

```yaml
# roles/ollama_runtime/defaults/main.yml
ollama_models: "{{ llm_model_registry | selectattr('provider', 'eq', 'ollama') | map(attribute='name') | list }}"
```

This ensures the deployed Ollama instance has exactly the models declared in
the registry — no undeclared local models, no missing models.

### 6. n8n and Dify configuration

The `n8n_runtime` role's Ansible tasks set n8n credential environment variables
from the routing table:

```yaml
- name: Set n8n LLM credential from routing table
  ansible.builtin.set_fact:
    n8n_ollama_base_url: "{{ llm_routing['n8n-summarize'].primary | llm_endpoint(llm_model_registry) }}"
```

A custom filter `llm_endpoint` resolves model → endpoint URL from the registry.
This eliminates hardcoded Ollama URLs in n8n credentials.

The `dify_runtime` role receives `OPENAI_API_BASE` overridden to the Ollama
endpoint for `dify-rag-query` tasks, using the same registry lookup.

### 7. Cost tier enforcement

Agents with role `monitor-agent` or `config-diff-agent` are prohibited from
routing to `cost_tier: high` models even as fallback. This is enforced by
`llm_router.py resolve` which rejects routes where:

```
requested_role.cost_tier_cap < resolved_model.cost_tier
```

`config/agent-policies.yaml` gains a `cost_tier_cap` field per agent role.

## Places That Need to Change

### `config/llm-model-registry.yaml` (new)

Full model registry as above.

### `config/llm-routing.yaml` (new)

Full routing table as above.

### `scripts/llm_router.py` (new)

Layer 1 tool per ADR 0345. Commands: `resolve`, `health`, `budget`.

### `roles/ollama_runtime/defaults/main.yml`

Source `ollama_models` from registry.

### `roles/n8n_runtime/tasks/main.yml`

Set n8n credential env vars via registry lookup.

### `roles/dify_runtime/tasks/main.yml`

Set `OPENAI_API_BASE` for Dify's Ollama-compatible backend from registry.

### `plugins/filter/platform_facts.py`

Add `llm_endpoint(model_name, registry)` filter.

### `config/agent-policies.yaml`

Add `cost_tier_cap` and `max_tokens_per_session` per agent role.

### `tests/test_llm_routing.py` (new)

Validates: all routes reference registered models; fallbacks exist; cost tier
caps are not violated; all Ollama models in registry are in `ollama_models`.

### `docs/runbooks/llm-inference-routing.md` (new)

How to add a model, change routing, check health, debug budget exhaustion.

## Consequences

### Positive

- Every LLM call is routed through declared policy — no agent makes an
  undeclared, uncapped, expensive API call.
- Local Ollama inference is used for low-capability tasks, reducing API spend.
- Model changes (e.g., upgrading from Haiku 4.5 to a newer model) require
  only a registry update, not hunting through n8n credentials and Dify settings.
- Token budget exhaustion is explicit and auditable rather than silent context
  overflow.

### Negative / Trade-offs

- Routing table adds a layer of indirection — operators must update both the
  model registry and routing table when adding a model.
- Health-check-based fallback adds latency to the first call of a session
  (one additional HTTP probe).
- Token counting is approximate and model-dependent; the per-session budget
  may be exceeded if counting discrepancies exist between the router's estimate
  and the model's actual consumption.
- Cost tier enforcement is a soft guarantee — it prevents routing policy
  violations but does not prevent agents from making many small calls that
  add up to high spend.

## Related ADRs

- ADR 0343: Operator Tool Interface Contract
- ADR 0344: Single-Source Environment Topology
- ADR 0345: Layered Operator Tool Separation
- ADR 0348: Per-Service LLM Context File
- ADR 0349: Agent Capability Manifest and Peer Discovery
- ADR 0352: Token-Budgeted Agent Onboarding Packs
- ADR 0354: Structured Agent Mutation Audit Log
