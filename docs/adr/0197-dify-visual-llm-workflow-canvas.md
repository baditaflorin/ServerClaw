# ADR 0197: Dify - Visual LLM Workflow and Agent Canvas

- Status: Implemented
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.48
- Implemented In Platform Version: 0.130.42
- Implemented On: 2026-03-28
- Date: 2026-03-27

## Context

LLM workflows in Windmill are written as Python code. There is no way for a human to visually inspect, edit, or design a multi-step agent workflow without reading source code. New agent patterns require a developer; there is no visual authoring surface. Iterating on prompt chains, tool sequences, and retrieval-augmented pipelines is slow and opaque.

## Decision

Deploy Dify on `docker-runtime-lv3` at `agents.lv3.org` behind the shared Keycloak-backed edge authentication flow. Connect Dify to:

- Ollama for local model inference on the private runtime network
- external LLM APIs through controller-managed credentials mirrored into the Dify runtime
- a Dify-local Qdrant sidecar for branch-safe knowledge-base support until ADR 0198 is merged on `main`
- the platform API gateway as a governed custom tool endpoint for the named tool registry
- Langfuse for workflow trace capture after apps are created and promoted

The platform's named tools are published from `config/agent-tool-registry.json` into Dify via `scripts/sync_tools_to_dify.py`. Dify workflows that graduate from experimentation to production are exported as YAML or JSON artifacts, committed to `platform/dify-workflows/`, and then executed through Windmill HTTP triggers rather than running as long-lived production logic inside Dify.

## Consequences

### Positive

- Non-developers can design, inspect, and iterate on multi-step LLM workflows visually.
- Dify's canvas makes prompt chains, branching, retrieval, and tool calls inspectable at a glance.
- Langfuse captures governed Dify workflow traces without requiring direct application-code instrumentation.
- Repo automation can bootstrap Dify setup, custom tools, and smoke workflows repeatably.

### Trade-offs

- Dify introduces a second workflow runtime alongside Windmill, so promotion boundaries must stay explicit.
- A branch-local Dify rollout cannot safely claim the shared ADR 0198 vector service until that ADR lands on `main`.
- Some Dify provider credentials remain controller-local secrets rather than fully declarative repo data.

## Boundaries

- Dify is the visual authoring surface; Windmill remains the production execution runtime.
- Infrastructure-touching workflows must be promoted into Windmill before production use.
- This workstream deploys a Dify-local Qdrant sidecar only; the shared `vectors.lv3.org` surface remains ADR 0198 work.

## Live Apply Notes

- The branch-local live apply converged Dify on `docker-runtime-lv3` and moved the internal listener to `8094` because `8093` was already occupied by the existing Plane proxy on the same guest.
- Internal verification was completed through an SSH tunnel to `docker-runtime-lv3`, where `/healthz`, `/console/api/setup`, and the bootstrap flow all succeeded and the smoke workflow export was written to `platform/dify-workflows/lv3-dify-smoke.yml`.
- The rebased current-main replay from `codex/ws-0197-main-finish` re-ran `make converge-dify` and `make converge-api-gateway`, after which `https://agents.lv3.org/healthz` returned `HTTP/2 200`, `https://api.lv3.org/v1/health` returned the expected canonical `HTTP/2 401` auth envelope, and `POST https://api.lv3.org/v1/dify-tools/get-platform-status` returned `HTTP/2 200` again with the governed platform-status payload.
- The linked-worktree smoke verification now succeeds without a shared-repo override: `scripts/dify_smoke.py` automatically falls back to the common repository `.local/langfuse/` directory, completed with `tool_count: 11`, and re-verified `trace_configured: true` from the isolated worktree.
- The integrated `main` release is `0.177.48`, which records the public Dify edge replay, the mainline receipt `2026-03-28-adr-0197-dify-mainline-live-apply`, and the packaged API gateway runbook compatibility repair directly in canonical repository state.

## Related ADRs

- ADR 0044: Windmill
- ADR 0146: Langfuse
- ADR 0198: Qdrant
