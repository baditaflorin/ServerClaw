# ADR 0287: LiteLLM As The Unified LLM API Proxy And Router

- Status: Deprecated
- Superseded By: ADR 0294
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform exposes LLM inference through Ollama (ADR 0145), which serves
models over its own HTTP API. As the number of LLM consumers grows (Dify,
Open WebUI, n8n, Windmill, ServerClaw, RAG context, Whisper ASR call chains),
several operational problems emerge:

- each consumer is hardcoded to Ollama's native API format; switching,
  augmenting, or fallback-routing to a different backend requires per-consumer
  changes
- there is no central point to apply rate limiting, per-consumer token budgets,
  or cost tracking across all LLM calls
- Langfuse (ADR 0146) captures traces per-integration; there is no aggregate
  view of total model utilisation across all consumers in one place
- some models are better suited to specific task types (coding, summarisation,
  embedding) but routing is done manually or not at all
- if a model is loading or unavailable, consumers fail with no retry or
  fallback path

LiteLLM is a CPU-only Python proxy that presents a single OpenAI-compatible
API endpoint to all consumers and translates requests to any configured
backend (Ollama, OpenAI, Anthropic, local GGUF, etc.). It handles routing,
retries, fallbacks, per-model budget limits, and OpenTelemetry-compatible
usage logging.

## Decision

We will deploy **LiteLLM** as the unified LLM API proxy and router.

### Deployment rules

- LiteLLM runs as a Docker Compose service on the docker-runtime VM
- it is the single LLM endpoint that all platform services call; direct
  calls to the Ollama API from services other than LiteLLM itself are
  deprecated and removed over time
- LiteLLM uses PostgreSQL as its usage tracking database following the
  existing shared database pattern (ADR 0042)
- secrets (API keys for any external model providers) are injected from
  OpenBao following ADR 0077
- the proxy is exposed on the guest network and optionally via the API
  gateway for agent mesh access

### Routing model

- models are declared in the LiteLLM config (tracked in the Ansible role)
  with an alias, a backend target, and capability tags (e.g. `coding`,
  `embedding`, `summarisation`, `vision`)
- consumers call a model alias, not a specific backend endpoint, so backend
  changes are transparent to consumers
- a fallback chain is declared per alias: if the primary Ollama model is
  loading, LiteLLM retries on a configured fallback model
- embedding requests are always routed to the Ollama embedding model; no
  external embedding API is used

### Observability integration

- LiteLLM emits usage events to Langfuse (ADR 0146) via the standard callback
  integration; per-consumer token counts and latency are visible in Langfuse
- LiteLLM exposes a `/metrics` endpoint consumed by Prometheus for aggregate
  request rate and error rate tracking in Grafana

## Consequences

**Positive**

- All LLM consumers gain model fallback and retry without per-consumer code
  changes.
- A single config file in the Ansible role defines the entire model routing
  table for the platform; adding or swapping a model is a one-line change.
- Rate limiting and per-consumer token budgets prevent runaway automation from
  saturating Ollama and degrading interactive workloads.
- The OpenAI-compatible API surface means standard LLM client libraries
  require only a `base_url` change to point at LiteLLM.

**Negative / Trade-offs**

- LiteLLM is an additional hop in every LLM call path; it adds ~5–20 ms proxy
  overhead per request.
- If LiteLLM is unavailable, all LLM-dependent services fail simultaneously;
  it becomes a single point of failure that must have a fast restart path.

## Boundaries

- LiteLLM is the LLM API proxy only; it does not store model weights, run
  inference, or replace Ollama as the inference engine.
- LiteLLM does not replace Langfuse for evaluation, annotation, or trace
  detail; it supplies usage events to Langfuse.
- LiteLLM does not manage the Whisper ASR (ADR 0285) or Piper TTS (ADR 0284)
  services; those are not LLM inference endpoints.

## Related ADRs

- ADR 0042: PostgreSQL as the shared relational database
- ADR 0077: Compose secrets injection pattern
- ADR 0095: API gateway as the unified platform entry point
- ADR 0145: Ollama for local LLM inference
- ADR 0146: Langfuse for agent observability
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3

## References

- <https://docs.litellm.ai/docs/>
