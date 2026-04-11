# ADR 0394: Integrate LibreChat Agents API for Programmatic Agent Access

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-10
- Concern: Agent Discovery, Platform Integration, Automation
- Depends on: ADR 0395 (Agent Interface Abstraction Layer)
- Tags: librechat, agents-api, open-responses, openai-compatible, serverclaw, automation

---

## Context

LibreChat has released a beta Agents API that exposes our ServerClaw agents
through two standardised interfaces:

1. **OpenAI-compatible Chat Completions** — `POST /api/agents/v1/chat/completions`
2. **Open Responses API** — `POST /api/agents/v1/responses`

Today, our agents are only accessible through the LibreChat web UI. External
consumers — n8n workflows, Dify tool chains, CLI scripts, monitoring hooks,
scheduled tasks, and the API gateway itself — cannot invoke a ServerClaw agent
conversationally. They can call individual tools via the Dify tools bridge
(`/v1/dify-tools/{tool_name}`), but they cannot start an agentic session that
reasons across multiple tools.

### What the Agents API unlocks

| Consumer | Current path | With Agents API |
|---|---|---|
| n8n workflows | Call individual tools via HTTP | Start an agent session that reasons across tools |
| Scheduled automation | Shell scripts calling tool endpoints | Agent-driven runbook execution with judgment |
| API gateway clients | No agent access | Full conversational agent via OpenAI SDK |
| Dify orchestrations | Tool-level calls only | Nested agent invocations |
| CLI / developer tools | Web UI only | `openai.chat.completions.create(model="agent_serverclaw_ops")` |
| External services | No access | Authenticated API access with token tracking |

### Why now

- The Agents API supports streaming, which is critical for long-running
  agentic operations (shell commands, convergence monitoring).
- Token usage tracking integrates with our existing cost-control model.
- Open Responses is being adopted as the standard for agentic workflows,
  giving us future compatibility with tooling from the broader ecosystem.
- Our bootstrap script (`scripts/bootstrap_librechat_agents.py`) already
  creates agents with stable IDs (`agent_serverclaw_ops`, etc.), making
  programmatic invocation straightforward.

---

## Decision

Integrate the LibreChat Agents API as a first-class platform capability,
exposed through the API gateway with authentication, rate limiting, and
audit logging.

### Phase 1: Enable and Configure (librechat_runtime role)

Update the LibreChat configuration to enable the `remoteAgents` interface:

```yaml
# In librechat.yaml.j2
interface:
  remoteAgents:
    use: true
    create: false   # Only bootstrap script creates agents
```

Generate a platform-level API key during deployment (stored in OpenBao) for
service-to-service agent calls. User-generated keys remain available through
the LibreChat UI for interactive use.

### Phase 2: API Gateway Route

Add an agent proxy route to the API gateway (`scripts/api_gateway/main.py`):

```
POST /v1/agents/chat/completions  → LibreChat /api/agents/v1/chat/completions
POST /v1/agents/responses         → LibreChat /api/agents/v1/responses
GET  /v1/agents/models            → LibreChat /api/agents/v1/models
```

The gateway:
- Authenticates callers via the existing `X-LV3-Dify-Api-Key` header or a
  new `Authorization: Bearer <key>` scheme.
- Maps internal platform identity to the LibreChat API key (service accounts
  share a single platform key; per-user keys remain optional).
- Emits audit events for every agent invocation (agent ID, caller, timestamp).
- Applies rate limiting per caller class (service: 60 req/min, user: 20 req/min).

### Phase 3: Bootstrap Script Updates

Extend `scripts/bootstrap_librechat_agents.py` to:
1. Verify the Agents API is reachable after bootstrap (smoke test via
   `/api/agents/v1/models`).
2. Output a stable agent-ID-to-capability mapping for consumers.
3. Register the Agents API endpoint in the platform service catalog.

### Phase 4: Consumer Integration

Provide a thin Python client at `platform/clients/agent_client.py` that wraps
the OpenAI SDK with platform defaults:

```python
from platform.clients.agent_client import get_agent_client

client = get_agent_client()  # reads gateway URL + API key from env/OpenBao
response = client.chat.completions.create(
    model="agent_serverclaw_ops",
    messages=[{"role": "user", "content": "Check disk usage on postgres"}],
    stream=True,
)
```

This client is the integration point for n8n HTTP nodes, Dify tool handlers,
scheduled tasks, and CLI utilities. It must go through the abstraction layer
defined in ADR 0395 so the underlying provider can be swapped.

### Phase 5: Health and Observability

- Add a health probe to `config/health-probe-catalog.json` for the Agents API
  endpoint.
- Add a Grafana dashboard panel showing agent invocations, latency, and
  token spend.
- Wire alerting for API key expiry and sustained error rates.

### Configuration Surface

| Setting | Source | Default |
|---|---|---|
| `librechat_agents_api_enabled` | role defaults | `true` |
| `librechat_agents_api_key` | OpenBao secret | generated at deploy |
| `librechat_agents_rate_limit_service` | role defaults | `60` |
| `librechat_agents_rate_limit_user` | role defaults | `20` |
| `librechat_remote_agents_create` | role defaults | `false` |

---

## Consequences

**Positive:**
- Agents become programmable infrastructure — any service can start an agentic
  session, not just users in the web UI.
- OpenAI SDK compatibility means zero learning curve for consumers.
- Token tracking gives cost visibility per caller.
- Audit logging provides compliance-grade traceability for agent actions.
- Open Responses alignment positions us for ecosystem tooling convergence.

**Negative / Trade-offs:**
- The Agents API is beta; breaking changes may require gateway adapter updates.
  Mitigated by the abstraction layer (ADR 0395) and pinning the API version
  in the gateway route.
- A platform API key with agent access has a wider blast radius than individual
  tool keys. Mitigated by rate limiting and audit logging.
- Agent sessions consume more tokens than direct tool calls. Token budgets must
  be set per consumer to prevent runaway spend.

---

## Related

- ADR 0395 — Agent Interface Abstraction Layer (decoupled DTO contract)
- ADR 0294 — One-API introduction (deprecated, but established the proxy pattern)
- ADR 0390 — Remove Open WebUI (consolidated agent UX into LibreChat)
- `scripts/bootstrap_librechat_agents.py` — agent bootstrap implementation
- `scripts/generate_librechat_tool_specs.py` — tool OpenAPI generation
- `config/agent-tool-registry.json` — canonical tool definitions
