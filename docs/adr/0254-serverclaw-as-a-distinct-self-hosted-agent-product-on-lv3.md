# ADR 0254: ServerClaw As A Distinct Self-Hosted Agent Product On LV3

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

The repository already contains many of the building blocks that an
OpenClaw-like product needs:

- Dify for visual agent and workflow authoring
- Open WebUI for operator and agent workbench access
- Windmill for browser-first and API-first routine operations
- Langfuse for agent observability
- Qdrant plus local search for retrieval
- Keycloak, OpenBao, and the governed tool registry for identity and control

What it still does not provide is one coherent product surface that behaves
like a self-hosted personal agent system:

- chat-first instead of ops-portal-first interaction
- workspace-scoped skills and memory
- long-running user-facing sessions
- channel adapters and personal-data connectors as one bounded runtime

## Decision

We will define **ServerClaw** as a distinct product surface on top of the LV3
platform.

### Product shape

- ServerClaw is the user-facing assistant product.
- LV3 remains the underlying control plane, security boundary, and governance
  layer.
- Dify remains the visual authoring surface.
- Open WebUI remains the operator workbench.
- Windmill remains the routine browser-first operations surface.

### Required product properties

ServerClaw must provide:

- chat-first interaction through governed messaging channels
- workspace-scoped assistants, skills, memory, and connector state
- server-resident execution that survives beyond one laptop or one chat
  session
- explicit delegation, approval, and audit boundaries when actions cross from
  personal-assistant behavior into platform mutation

### Upstream relationship

ServerClaw may adopt upstream OpenClaw concepts, compatible formats, and proven
interaction patterns, but it is **not** required to run the upstream OpenClaw
codebase unchanged.

## Consequences

**Positive**

- The repository gains one honest product target instead of a loose collection
  of agent-adjacent services.
- Existing LV3 control-plane investments can be reused without pretending the
  ops portal is already a personal assistant product.
- Future decisions can be judged by whether they improve the ServerClaw
  product surface rather than only adding another internal tool.

**Negative / Trade-offs**

- The platform now has to support both operator-facing and user-facing agent
  surfaces with clearer separation of concerns.
- Product vocabulary, tenancy, and data ownership will need more deliberate
  governance than the current single-operator estate.

## Boundaries

- This ADR does not claim the repository now runs upstream OpenClaw.
- This ADR does not rename every existing LV3 service into ServerClaw.
- ServerClaw is not a public anonymous chatbot surface; identity, delegation,
  and audit remain mandatory.

## Related ADRs

- ADR 0060: Open WebUI for operator and agent workbench
- ADR 0069: Agent tool registry and governed tool calls
- ADR 0197: Dify visual LLM workflow and agent canvas
- ADR 0205: Capability contracts before product selection
- ADR 0224: Server-resident operations as the default control model

## References

- <https://docs.openclaw.ai/start/setup>
- <https://docs.openclaw.ai/gateway/multiple-gateways>
- <https://docs.openclaw.ai/tools/skills>
