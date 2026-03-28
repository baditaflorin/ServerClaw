# ADR 0197: Dify - Visual LLM Workflow and Agent Canvas

- Status: Implemented
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.27
- Implemented In Platform Version: 0.130.31
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
- The governed Dify tool bridge is live through `api.lv3.org`; `POST /v1/dify-tools/get-platform-status` now succeeds with the Dify tools API key and returns the governed platform-status payload.
- The integrated `main` release is `0.177.27`, which records the repo-managed Dify runtime, the governed tool bridge, the committed smoke workflow export, and the branch-local live-apply receipt directly in canonical repository state.
- Public `agents.lv3.org` hostname publication remains blocked outside the repo by the Hetzner DNS write brownout, so the public edge hostname still needs a follow-up replay from `main` once the provider-side DNS API recovers.

## Related ADRs

- ADR 0044: Windmill
- ADR 0146: Langfuse
- ADR 0198: Qdrant
