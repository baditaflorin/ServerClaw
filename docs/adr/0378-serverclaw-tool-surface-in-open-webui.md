# ADR 0378: ServerClaw Tool Surface In Open WebUI

- Status: Proposed
- Implementation Status: Implemented
- Date: 2026-04-06

## Context

ADR 0377 gives the chatbot at `chat.lv3.org` knowledge about the platform
(it can *answer* questions). This ADR addresses the second half: making the
chatbot able to *act* — query live state, look up containers, check
deployment history, and eventually execute governed operations.

The platform already has 32 governed tools registered in
`config/agent-tool-registry.json`. These tools are categorized as:

- **Observe** (19 tools): read-only queries like `get-platform-status`,
  `list-containers`, `get-container-logs`, `search-outline-documents`,
  `list-plane-tasks`, `query-platform-context`
- **Execute** (11 tools): mutating operations like `run-governed-command`,
  `create-plane-task`, `create-outline-document`, `browser-run-session`
- **Approve** (1 tool): `check-command-approval` for governance gates

Today these tools are only accessible through:

- Direct script invocation on the controller
- Dify workflow steps
- MCP export (`--export-mcp`) for Claude Code sessions

They are **not** accessible from Open WebUI chat sessions, which means a
user asking "what containers are running?" gets a hallucinated answer
instead of live data.

Open WebUI supports **Functions** (Python plugins that can act as tools,
filters, or pipes) and **Tool Servers** (OpenAPI-compatible external
endpoints). Either mechanism can bridge the governed tool registry into
chat sessions.

## Decision

We will expose ServerClaw governed tools in Open WebUI in two phases.

### Phase 1: Observe Tools as Open WebUI Functions

Start with read-only observe tools that carry no mutation risk:

| Tool | What it gives the chatbot |
|------|--------------------------|
| `get-platform-status` | Current platform health and service states |
| `list-containers` | Running containers on any host |
| `get-container-logs` | Recent logs from a specific container |
| `get-deployment-history` | What was deployed recently and when |
| `list-recent-receipts` | Evidence of recent live-applies |
| `query-platform-context` | Semantic search over platform docs |
| `list-plane-tasks` | Current tasks in the agent task board |
| `search-outline-documents` | Search the wiki |
| `list-serverclaw-skills` | What skills are available |

**Implementation approach — Tool Server (preferred):**

1. Create a lightweight HTTP tool server on the controller that wraps
   `scripts/agent_tool_registry.py` handlers behind an OpenAPI-compatible
   endpoint
2. The tool server authenticates requests using the same approle/token
   mechanism that other services use
3. Register this tool server in Open WebUI's admin configuration
4. Each tool appears as a callable function in chat — when the model
   decides to call `get-platform-status`, the tool server executes it and
   returns structured results

**Alternative approach — Open WebUI Functions:**

If the tool server approach proves too complex for Phase 1, implement each
observe tool as a standalone Open WebUI Function (Python file uploaded via
the admin UI or API). Each function calls the controller's tool endpoint
or runs the underlying script via SSH.

**Why tool server is preferred:** Single deployment point, no per-tool
Python files to manage in Open WebUI, automatic OpenAPI schema generation,
and the same endpoint can serve MCP clients and Dify.

### Phase 2: Execute Tools with Approval Gates

Once Phase 1 is stable, extend to execute-category tools with governance:

1. Execute tools require explicit user confirmation in the chat UI before
   running (Open WebUI supports confirmation dialogs for tool calls)
2. Every execute tool call is logged to Langfuse with the user identity,
   tool name, parameters, and result
3. High-impact tools (`run-governed-command`, `dispatch-nomad-job`) require
   the `check-command-approval` gate — the chatbot must call the approval
   tool first and only proceed if approved
4. Tool results are streamed back into the chat as structured messages

### Skill-Aware Model Routing

Different conversations may need different capabilities:

1. Define Open WebUI **model presets** that bundle specific tool sets:
   - `serverclaw-observe`: All observe tools, platform system prompt, RAG
   - `serverclaw-ops`: Observe + execute tools, operator-level prompt
   - `serverclaw-chat`: No tools, just RAG knowledge (safe for guests)
2. Default new users to `serverclaw-chat`; operators get `serverclaw-ops`
3. Map these presets to Keycloak roles so tool access follows SSO groups

### Tool Server Architecture

```
chat.lv3.org (Open WebUI)
    │
    ├── RAG queries ──► Qdrant (platform_context)
    │
    └── Tool calls ──► Tool Server (controller:8095)
                           │
                           ├── observe handlers (no auth gate)
                           ├── execute handlers (approval gate)
                           └── audit log ──► Langfuse
```

The tool server:

- Runs on `runtime-control-lv3` alongside the existing controller services
- Exposes an OpenAPI spec auto-generated from `agent-tool-registry.json`
- Authenticates Open WebUI requests via a service token stored in OpenBao
- Logs all invocations to Langfuse for observability
- Returns structured JSON that the model can format for the user

### Ansible Role Changes

1. **New role: `serverclaw_tool_server`** — Deploys the tool server as a
   systemd service or Docker container on the controller
2. **Update `open_webui_runtime`** — Add tool server URL configuration,
   model preset definitions, and system prompt with tool descriptions
3. **Update `keycloak_runtime`** — Map Keycloak roles to Open WebUI model
   preset access levels

## Consequences

### Positive

- Users can ask "what containers are running?" and get a live, accurate
  answer instead of a hallucination
- Operators can check deployment history, search docs, and query tasks
  without leaving the chat interface
- The same tool server serves Open WebUI, MCP clients, and Dify — single
  implementation, multiple consumers
- Governance model (observe/execute/approve) is preserved end-to-end
- Audit trail via Langfuse covers all tool invocations regardless of
  which frontend triggered them

### Negative

- Tool server is a new service to maintain and monitor
- Llama 3.2 3B may struggle with reliable tool calling — may need to
  upgrade to a model with stronger function-calling capabilities
  (Qwen 2.5 7B, Llama 3.1 8B, or Mistral 7B Instruct)
- Phase 2 execute tools introduce operational risk through the chat
  interface — mitigated by approval gates and role-based access

### Risks

- Tool server availability affects chat quality — if the tool server is
  down, the chatbot falls back to RAG-only answers (graceful degradation)
- Model may call tools unnecessarily or with wrong parameters — mitigated
  by structured schemas and confirmation dialogs for execute tools
- Token/auth misconfiguration could block all tool calls — mitigated by
  health checks and convergence-time verification

## Dependencies

- ADR 0377 (Platform Knowledge Integration) — provides the knowledge layer
- ADR 0069 (Agent Tool Registry) — defines the tool catalog
- ADR 0254 (ServerClaw) — product identity and governance model
- ADR 0257 (Skill Packs) — skill discovery for the chatbot
- ADR 0146 (Langfuse) — audit logging for tool invocations
- ADR 0060 (Open WebUI) — the integration target

## Open Questions

1. **Model upgrade**: Should we upgrade from Llama 3.2 3B to a model with
   better tool-calling support as part of this work, or treat it as a
   separate ADR?
2. **Tool server vs. MCP**: Open WebUI is adding MCP support — should we
   wait for native MCP and use the existing `--export-mcp` surface instead
   of building a custom tool server?
3. **Rate limiting**: Should tool calls be rate-limited per user to prevent
   abuse, or is role-based access sufficient?
