# ADR 0145: Ollama for Local LLM Inference API

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.121.0
- Implemented In Platform Version: 0.114.7
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

The platform already had several repo-managed surfaces that benefit from local inference:

- Open WebUI needs a private model source for operator queries that do not require an external API.
- The goal compiler benefits from a bounded fallback when a free-form instruction misses the deterministic rule set.
- Agent tooling needs a shared client that can route local inference consistently and record observability events.

Sending those prompts to external providers by default adds unnecessary privacy exposure, an external availability dependency, and extra latency for short, bounded tasks.

## Decision

We run Ollama as a private, repo-managed runtime on `docker-runtime-lv3`.

### Runtime shape

- service id: `ollama`
- runtime host: `docker-runtime-lv3`
- publication model: private-only on port `11434`
- persistent model storage: `/data/ollama/models`
- pinned image: `docker.io/ollama/ollama:0.18.2@sha256:1550310a86dbfd206a0319b3e1580e4a8edb0000963ca7550af1b7ed57e4c87f`
- startup model: `llama3.2:3b`

The runtime is converged through `roles/ollama_runtime` and `playbooks/ollama.yml`. Startup models are declared in `config/ollama-models.yaml` and pulled during converge through the Ollama API.

### Shared LLM client

`platform/llm/client.py` is the platform entry point for local inference. It:

- loads the repo-managed model catalog
- routes supported use cases to Ollama when the declared model is available
- optionally falls back to an OpenAI-compatible endpoint when explicitly configured
- records `llm.inference` events in the mutation ledger

### Goal compiler boundary

The goal compiler keeps deterministic rule matching as the primary path. Only unmatched input can call the shared LLM client, once, to rewrite the instruction into a shorter canonical form before retrying direct-workflow and rule matching. If Ollama is unavailable, compilation degrades back to the existing parse error.

### Open WebUI boundary

Open WebUI consumes the local model source through its repo-managed connector configuration:

- `ENABLE_OLLAMA_API=True`
- `OLLAMA_BASE_URL=http://host.docker.internal:11434`
- `DEFAULT_MODELS=llama3.2:3b`
- `DEFAULT_PINNED_MODELS=llama3.2:3b`

The compose template adds `host.docker.internal:host-gateway` so the Open WebUI container can reach the private Ollama listener without collapsing both services into one compose project.

## Implementation Notes

- The new service is wired into the image, workflow, command, dependency, health-probe, service-capability, completeness, and control-plane lane catalogs.
- `inventory/host_vars/proxmox_florin.yml` opens the private Ollama port for the guest network and private RFC1918 callers while keeping the service off the public edge.
- `scripts/ollama_probe.py` provides a simple three-run latency benchmark against `/api/generate`.
- The Open WebUI runtime now recovers from stale compose-network drift before retrying container startup, matching the existing Docker drift handling already used for other services.

## Consequences

### Positive

- Local model requests stay on the private platform network.
- Goal-compiler fallback now has a bounded local-normalisation path instead of immediately failing on every near-miss.
- Open WebUI exposes a repo-managed local model by default without depending on external API keys.
- The runtime is observable through health probes, the service catalogs, and `llm.inference` ledger events.

### Trade-offs

- CPU-only local inference is materially slower than frontier hosted APIs for some completions; the startup-model latency observed on `llama3.2:3b` was acceptable for bounded normalisation and operator workbench queries, but not a replacement for all model classes.
- Model files consume persistent disk and RAM on `docker-runtime-lv3`.
- The local model connector must remain explicitly scoped to safe use cases; this ADR does not authorize broad autonomous operational decisions by the model.

## Verification

The first live implementation on 2026-03-25 verified:

- `curl -fsS http://127.0.0.1:11434/api/version` returned `{"version":"0.18.2"}`
- `docker exec ollama ollama show llama3.2:3b` succeeded on `docker-runtime-lv3`
- the Open WebUI container could reach `http://host.docker.internal:11434/api/version`
- a three-run local generation probe against `llama3.2:3b` reported `min=2038.3ms`, `avg=2801.9ms`, `p95=4073.5ms`, `max=4073.5ms`

## Related ADRs

- ADR 0060: Open WebUI for operator and agent workbench
- ADR 0112: Deterministic goal compiler
- ADR 0115: Event-sourced mutation ledger
- ADR 0146: Langfuse for LLM agent observability
