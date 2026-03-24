# ADR 0146: Langfuse for LLM Agent Observability

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

As the platform adopts local LLM inference (ADR 0145) and agentic workflows that call language models for goal normalisation, triage context summarisation, and runbook interpretation, a new observability gap opens:

The existing mutation ledger (ADR 0115) records `llm.inference` events with basic fields (model, tokens, latency). But it does not capture:

- The **trace** of an agent's multi-step reasoning: which prompt led to which tool call, which tool result changed the next prompt.
- **Prompt quality metrics**: which prompts consistently produce structured, parseable output and which frequently produce malformed JSON or off-topic responses.
- **Cost breakdown**: which agent workflows consume the most tokens, and whether local Ollama models are successfully absorbing traffic that would otherwise go to the external API.
- **Latency percentiles**: p50/p95/p99 inference latency by model and use case.
- **Failure modes**: how often the LLM refuses, truncates, or produces output that fails the downstream parser.

Without this visibility, LLM-assisted agent workflows are a black box. When the triage engine's LLM normalisation produces a wrong intent compilation, there is no structured record of what prompt was used, what the model returned, and where the parsing failed.

**Langfuse** is a self-hosted, open-source LLM observability platform with a structured SDK that wraps LLM calls in traces, spans, and generations. It stores prompt/response pairs, latency, token counts, and evaluation scores in a Postgres database with a clean web UI and a REST API.

## Decision

We will deploy **Langfuse** on `docker-runtime-lv3` and instrument all platform LLM calls through the Langfuse SDK.

### Deployment

```yaml
# In versions/stack.yaml
- service: langfuse
  vm: docker-runtime-lv3
  image: langfuse/langfuse:latest
  port: 3010
  access: tailscale_only
  database: postgres-lv3    # Uses the platform Postgres instance
  keycloak_oidc: true
  subdomain: langfuse.lv3.org
```

Langfuse uses Postgres for trace storage (a dedicated `langfuse` database on `postgres-lv3`) and the existing Keycloak OIDC for operator login.

### SDK integration

The platform LLM client (ADR 0145) wraps every inference call in a Langfuse generation:

```python
# platform/llm/client.py (extended with Langfuse tracing)
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

langfuse = Langfuse(
    host="http://langfuse:3010",
    public_key=openbao.get("langfuse/public-key"),
    secret_key=openbao.get("langfuse/secret-key"),
)

class PlatformLLMClient:

    @observe(as_type="generation")
    def complete(self, prompt: str, use_case: str, max_tokens: int = 512) -> str:
        langfuse_context.update_current_observation(
            name=use_case,
            input=prompt,
            model=model.name,
            metadata={"provider": model.provider, "context_id": self.context_id},
        )
        result = self._call_model(prompt, model, max_tokens)
        langfuse_context.update_current_observation(
            output=result,
            usage={"input": prompt_tokens, "output": completion_tokens},
        )
        return result
```

Every agent session ties its LLM calls to a trace via the `context_id` from ADR 0123:

```python
# At session start, create a Langfuse trace for the session
trace = langfuse.trace(
    name=f"agent-session/{actor_id}",
    session_id=ctx.context_id,
    user_id=actor_id,
    metadata={"platform_version": manifest.platform_version},
)
```

### What is captured

| Data | Captured | Retention |
|---|---|---|
| Prompt text | Yes | 30 days |
| Model response text | Yes | 30 days |
| Token counts (input/output) | Yes | 90 days |
| Latency (ms) | Yes | 90 days |
| Model name and provider | Yes | 90 days |
| Use case / span name | Yes | 90 days |
| Parse success/failure | Yes (via scores) | 90 days |
| Session/context_id | Yes | 90 days |

After 30 days, prompt/response text is deleted (privacy: operational prompts may contain platform state). Aggregated metrics (token counts, latency, error rates) are retained for 90 days.

### Evaluation scores

After every LLM call, the caller scores the output with a structured evaluator:

```python
# goal_compiler/compiler.py
result = llm.complete(prompt, use_case="goal_compiler_normalisation")
parsed = try_parse_intent(result)
langfuse.score(
    trace_id=trace.id,
    name="parse_success",
    value=1.0 if parsed else 0.0,
    comment=f"parse_error: {parse_error}" if not parsed else None,
)
```

Evaluation scores are the primary signal for prompt quality monitoring. A dashboard in Langfuse shows parse success rate by use case over time. A score below 0.8 for any use case triggers a `platform.findings.llm_quality_degraded` finding to the observation loop.

### Cost dashboard

A Grafana dashboard (backed by Langfuse's API) shows:
- Tokens consumed per day: Ollama (free) vs. external API (charged).
- Cost trend: is local model adoption reducing external API spend?
- Latency comparison: Ollama p50/p95 vs. external API p50/p95.

## Consequences

**Positive**

- Every LLM-assisted agent decision is traceable from prompt to parsed output. When a triage engine mis-diagnoses a failure because the LLM returned an unexpected format, the trace shows exactly what happened.
- Evaluation scores provide a data-driven basis for improving prompts and deciding whether to increase local model use or fall back to a larger external model.
- The cost dashboard closes the feedback loop on ADR 0145's hypothesis: local models should reduce external API token spend.

**Negative / Trade-offs**

- Langfuse stores prompt and response text in Postgres. For 30 days. Prompts contain platform context (service names, recent mutations, alert content). This data is sensitive and must be covered by the same access controls as the rest of the platform.
- The SDK adds a small latency overhead to each LLM call (~5ms for the async trace write). For high-frequency calls this is negligible; for latency-sensitive interactive sessions it is barely measurable.
- Maintaining Langfuse as a service adds operational overhead. It requires monitoring, backup, and upgrades like any other Docker service.

## Boundaries

- Langfuse observes LLM calls that go through `platform/llm/client.py`. Direct calls to the Anthropic SDK or Ollama that bypass the platform client are not traced.
- Prompt and response text is retained for 30 days maximum and is never indexed in the search fabric (ADR 0121) or displayed in the changelog portal.

## Related ADRs

- ADR 0043: OpenBao (Langfuse API key storage)
- ADR 0056: Keycloak SSO (Langfuse operator login)
- ADR 0060: Open WebUI (operator LLM workbench; separate from Langfuse tracing)
- ADR 0115: Event-sourced mutation ledger (llm.inference events; Langfuse is the detailed view)
- ADR 0123: Agent session bootstrap (session context_id as Langfuse trace session)
- ADR 0145: Ollama (local inference; all Ollama calls traced through Langfuse)
