# WS-0377: Open WebUI Platform Knowledge and ServerClaw Tool Integration

## Goal

Transform `chat.lv3.org` from a generic chatbot into a platform-aware assistant
that knows what LV3 is, what services are deployed, and can query live state
through governed tools.

## ADRs

- **ADR 0377** — Wire platform knowledge (RAG, system prompt, knowledge docs)
  into Open WebUI so the chatbot can answer platform questions accurately
- **ADR 0378** — Expose ServerClaw governed tools through Open WebUI so the
  chatbot can query live platform state and (Phase 2) execute operations

## Phases

### Phase 1: Knowledge (ADR 0377)
- [ ] Configure Open WebUI RAG to use Qdrant `platform_context` collection
- [ ] Create platform-aware system prompt template
- [ ] Generate and upload service/tool/skill catalog documents
- [ ] Verify chatbot can answer "what services are running?" accurately

### Phase 2: Observe Tools (ADR 0378 Phase 1)
- [ ] Deploy tool server on controller wrapping observe-category tools
- [ ] Register tool server in Open WebUI
- [ ] Verify chatbot can call `get-platform-status` and return live data
- [ ] Add remaining observe tools

### Phase 3: Execute Tools (ADR 0378 Phase 2)
- [ ] Add execute tools with approval gates
- [ ] Map Keycloak roles to model preset access levels
- [ ] Audit logging to Langfuse for all tool invocations

## Open Questions

- Model upgrade: Llama 3.2 3B may not be capable enough for reliable RAG
  and tool calling — evaluate Qwen 2.5 7B or Llama 3.1 8B
- Open WebUI MCP support: May be able to use existing `--export-mcp`
  instead of building a custom tool server
