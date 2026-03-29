# ADR 0294: One-API As The Unified LLM API Proxy And Router

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

ADR 0287 selected LiteLLM for this role. LiteLLM was subsequently found to be
a supply-chain attack target: its large Python dependency tree (500+ transitive
packages) was exploited in a confirmed supply-chain compromise that injected
malicious code into published PyPI releases. ADR 0287 is deprecated.

The functional requirement is unchanged: the platform needs a single
OpenAI-compatible API endpoint in front of Ollama that provides:

- routing across model aliases without per-consumer backend changes
- per-consumer API keys and token quotas
- fallback and retry on model load failures
- aggregate usage visibility fed to Langfuse and Prometheus

One-API (`songquanpeng/one-api`) fulfils the same role. It is written in Go
and ships as a single self-contained binary. Its dependency surface is orders
of magnitude smaller than LiteLLM's Python package tree: the Go module graph
has under 30 direct dependencies, all statically linked at build time. There
is no pip, no PyPI, and no dynamic import surface. The compiled Docker image
is approximately 20 MB.

One-API has been in active production use in self-hosted LLM deployments since
2023, is MIT-licensed, and exposes a full OpenAI-compatible API with a
built-in management UI for channel and consumer key administration.

## Decision

We will deploy **One-API** as the unified LLM API proxy and router, superseding
ADR 0287.

### Deployment rules

- One-API runs as a Docker Compose service on the docker-runtime VM
- it uses PostgreSQL as its database backend (ADR 0042) for channel, token,
  and usage records
- secrets (admin password, session secret, Langfuse API key) are injected from
  OpenBao following ADR 0077
- the proxy is exposed on the guest network and via the API gateway for agent
  mesh access (ADR 0095)
- the Docker image is pinned to a specific SHA digest in the Ansible role; no
  floating `latest` tag is used

### Supply-chain hardening rules

- the Docker image digest is verified against a recorded baseline on every
  converge; a digest change is a blocking alert, not a silent update
- the image is pulled through Harbor (the platform's internal registry, ADR
  0068) which enforces Trivy CVE scanning before the image is admitted
- no Python interpreter or pip is present in the runtime container

### Routing model

- Ollama model endpoints are registered as One-API channels with alias names
  and capability tags (e.g. `coding`, `embedding`, `summarisation`)
- consumers call a channel alias through the One-API endpoint; backend
  changes are transparent to consumers
- fallback chains are configured per channel: if the primary Ollama model is
  loading, One-API retries on the declared fallback channel
- embedding requests are always routed to the Ollama embedding channel; no
  external embedding API is used unless explicitly declared

### Observability integration

- One-API's built-in usage logging writes token counts per consumer key to its
  PostgreSQL tables; a Windmill job exports these to Langfuse (ADR 0146) daily
- One-API's `/metrics` endpoint (Prometheus format) is scraped by Alloy for
  aggregate request rate and error rate visibility in Grafana

## Consequences

**Positive**

- The Go binary eliminates the PyPI supply-chain attack surface that caused
  the LiteLLM deprecation; there are no dynamic package installs at runtime.
- A static 20 MB image is significantly easier to audit, pin, and scan than
  a Python virtualenv with hundreds of transitive packages.
- All LLM consumers retain the same OpenAI-compatible API surface; migrating
  from LiteLLM requires only a `base_url` change.
- The management UI provides a visual channel and quota administration layer
  that does not require direct database access.

**Negative / Trade-offs**

- One-API's channel configuration is managed through its UI and API rather
  than a declarative config file; the Ansible role applies channels via the
  One-API management API on each converge, which is less idiomatic than a
  file-based config.
- One-API's observability export is less native than LiteLLM's built-in
  Langfuse callback; the Windmill export job adds a daily batch delay before
  usage data appears in Langfuse.

## Supply-Chain Incident Note

This ADR supersedes ADR 0287 specifically because LiteLLM's PyPI distribution
was confirmed as a supply-chain attack vector. Any future evaluation of
Python-based LLM tooling for the platform's critical path must include an
explicit supply-chain risk assessment before adoption.

## Boundaries

- One-API is the LLM API proxy only; it does not store model weights, run
  inference, or replace Ollama as the inference engine.
- One-API does not replace Langfuse for evaluation, annotation, or trace
  detail; it feeds aggregate token usage events to Langfuse.
- One-API does not manage Whisper ASR (ADR 0285) or Piper TTS (ADR 0284);
  those are not LLM inference endpoints.

## Related ADRs

- ADR 0042: PostgreSQL as the shared relational database
- ADR 0068: Container image policy
- ADR 0077: Compose secrets injection pattern
- ADR 0095: API gateway as the unified platform entry point
- ADR 0145: Ollama for local LLM inference
- ADR 0146: Langfuse for agent observability
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0287: LiteLLM as the unified LLM API proxy (deprecated, superseded by
  this ADR)

## References

- <https://github.com/songquanpeng/one-api>
