# ADR 0395: Agent Interface Abstraction Layer — Provider-Agnostic DTOs

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-10
- Concern: Platform Architecture, Agent Discovery, Decoupling
- Depends on: none
- Tags: dto, abstraction, decoupling, agents, provider-agnostic, librechat, clean-architecture

---

## Context

The platform currently has deep coupling to LibreChat as the agent runtime:

| Coupling point | What is hardcoded |
|---|---|
| `bootstrap_librechat_agents.py` | MongoDB document schema, LibreChat action format, agent document shape |
| `generate_librechat_tool_specs.py` | LibreChat's OpenAPI action convention, `operationId` naming |
| `librechat.yaml.j2` | LibreChat-specific config keys (`modelSpecs`, `endpoints`, `interface`) |
| `librechat_runtime` role | Container names, MongoDB, Meilisearch sidecars |
| `config/serverclaw/system-prompt.md` | Assumes LibreChat's tool-calling conventions |
| API gateway tool bridge | Dify-era naming (`/v1/dify-tools/`), Dify-era auth header |

If we decide to move from LibreChat to another agent runtime (Dify Agents,
LangGraph Cloud, CrewAI, a custom runtime, or a future platform), the migration
would touch every layer from deployment to API surface.

### What we want

A clean separation between:

1. **Platform contracts** — what an agent *is*, what tools it *has*, how
   callers *invoke* it, and what responses *look like*.
2. **Provider implementation** — how a specific runtime (LibreChat, Dify,
   custom) fulfills those contracts.

This is the Dependency Inversion Principle applied to agent infrastructure:
high-level platform code depends on abstractions, not on LibreChat internals.

---

## Decision

Introduce an **Agent Interface Abstraction Layer** consisting of:
1. Platform-level DTOs (data transfer objects) for agents, tools, and messages.
2. A provider adapter interface that maps DTOs to/from provider-specific formats.
3. Migration of all consumers to use DTOs instead of provider-specific types.

### Layer 1: Platform DTOs

Define canonical data structures in `platform/agents/dto.py`:

```python
@dataclass
class AgentDefinition:
    """Platform-canonical agent definition. Provider-agnostic."""
    agent_id: str                    # e.g. "agent_serverclaw_ops"
    name: str                        # Human-readable name
    description: str                 # What this agent does
    model: str                       # Model identifier (provider-resolved)
    system_prompt: str               # Instructions
    tool_pack_ids: list[str]         # References to tool packs
    capabilities: list[str]          # e.g. ["actions", "artifacts", "chain"]
    conversation_starters: list[str] # Suggested prompts
    metadata: dict                   # Extensible key-value pairs

@dataclass
class ToolDefinition:
    """Platform-canonical tool definition. Already exists in agent-tool-registry.json."""
    tool_name: str
    title: str
    description: str
    category: str                    # observe, govern, act
    input_schema: dict               # JSON Schema
    output_schema: dict              # JSON Schema
    transport: str                   # controller_local, http, etc.
    endpoint: str                    # Handler reference
    requires_approval: bool
    audit_on_call: bool

@dataclass
class AgentMessage:
    """A single message in an agent conversation."""
    role: str                        # user, assistant, system, tool
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

@dataclass
class ToolCall:
    """A tool invocation within a message."""
    id: str
    tool_name: str
    arguments: dict

@dataclass
class AgentRequest:
    """Platform-canonical request to invoke an agent."""
    agent_id: str
    messages: list[AgentMessage]
    stream: bool = True
    max_tokens: int | None = None
    caller_identity: str = ""        # For audit trail

@dataclass
class AgentResponse:
    """Platform-canonical response from an agent invocation."""
    agent_id: str
    message: AgentMessage
    usage: TokenUsage | None = None
    finish_reason: str = ""          # stop, tool_calls, length, error

@dataclass
class TokenUsage:
    """Token consumption for cost tracking."""
    input_tokens: int
    output_tokens: int
    cache_tokens: int = 0
    total_tokens: int = 0

@dataclass
class AgentStreamChunk:
    """A single chunk in a streaming agent response."""
    agent_id: str
    delta_content: str | None = None
    delta_tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
```

### Layer 2: Provider Adapter Interface

Define `platform/agents/provider.py`:

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class AgentProvider(ABC):
    """Interface that every agent runtime must implement."""

    @abstractmethod
    async def invoke(self, request: AgentRequest) -> AgentResponse:
        """Synchronous (non-streaming) agent invocation."""

    @abstractmethod
    async def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamChunk]:
        """Streaming agent invocation."""

    @abstractmethod
    async def list_agents(self) -> list[AgentDefinition]:
        """Return all available agents."""

    @abstractmethod
    async def register_agent(self, agent: AgentDefinition) -> None:
        """Register or update an agent in the runtime."""

    @abstractmethod
    async def deregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the runtime."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the provider is operational."""
```

### Layer 3: LibreChat Provider Implementation

Create `platform/agents/providers/librechat.py`:

```python
class LibreChatProvider(AgentProvider):
    """Maps platform DTOs to/from LibreChat's APIs."""

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url
        self._api_key = api_key
        self._client = OpenAI(base_url=f"{base_url}/api/agents/v1", api_key=api_key)

    async def invoke(self, request: AgentRequest) -> AgentResponse:
        messages = [self._to_openai_message(m) for m in request.messages]
        resp = self._client.chat.completions.create(
            model=request.agent_id,
            messages=messages,
            stream=False,
        )
        return self._from_openai_response(request.agent_id, resp)

    async def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamChunk]:
        messages = [self._to_openai_message(m) for m in request.messages]
        for chunk in self._client.chat.completions.create(
            model=request.agent_id,
            messages=messages,
            stream=True,
        ):
            yield self._from_openai_chunk(request.agent_id, chunk)

    async def register_agent(self, agent: AgentDefinition) -> None:
        # Delegates to bootstrap_librechat_agents.py logic
        # Maps AgentDefinition → MongoDB document
        ...

    # ... private mapping methods ...
```

### Layer 4: Provider Registry and Resolution

In `platform/agents/registry.py`:

```python
_providers: dict[str, AgentProvider] = {}

def register_provider(name: str, provider: AgentProvider) -> None:
    _providers[name] = provider

def get_provider(name: str | None = None) -> AgentProvider:
    if name is None:
        name = os.environ.get("LV3_AGENT_PROVIDER", "librechat")
    return _providers[name]
```

Configuration via environment variable or role defaults:

```yaml
# In inventory or role defaults
lv3_agent_provider: librechat   # or: dify, langgraph, custom
```

### Migration Path

| What changes | Before (coupled) | After (abstracted) |
|---|---|---|
| Agent bootstrap | Writes MongoDB documents directly | Calls `provider.register_agent(AgentDefinition(...))` |
| Tool spec generation | Produces LibreChat-specific OpenAPI | Produces platform ToolDefinition list; provider adapter generates format-specific specs |
| API gateway agent routes | Proxies raw LibreChat HTTP | Calls `provider.invoke()` / `provider.stream()` with DTOs |
| n8n / external consumers | Must know LibreChat URL + format | Calls gateway with platform DTOs |
| System prompts | Stored in LibreChat config | Stored in platform config; injected by provider adapter |
| Health probes | LibreChat-specific HTTP check | Calls `provider.health_check()` |

### File Layout

```
platform/
├── agents/
│   ├── __init__.py
│   ├── dto.py              # AgentDefinition, AgentRequest, AgentResponse, etc.
│   ├── provider.py         # AgentProvider ABC
│   ├── registry.py         # Provider registration and resolution
│   └── providers/
│       ├── __init__.py
│       ├── librechat.py    # LibreChat Agents API adapter
│       └── stub.py         # Test/dev stub provider
```

### What Does NOT Change

- **`config/agent-tool-registry.json`** — Already provider-agnostic. This is
  the canonical tool definition source and stays as-is.
- **`config/serverclaw/skill-packs.yaml`** — Pack groupings are platform
  concepts, not provider concepts.
- **API gateway tool bridge** (`/v1/dify-tools/`) — Tool execution is already
  decoupled from the agent runtime. Tools run on the gateway regardless of
  which agent runtime invokes them.

### Naming Conventions

The existing `dify-tools` naming in the API gateway endpoint path is a
historical artifact from the Dify era. As part of this work:

- **Do not rename** the existing `/v1/dify-tools/` path (breaking change for
  active consumers).
- **Add** `/v1/tools/` as an alias that proxies to the same handlers.
- **New code** references the `/v1/tools/` path.
- **Deprecate** `/v1/dify-tools/` in a future ADR once all consumers migrate.

Similarly, rename the auth header in new routes:
- New: `Authorization: Bearer <key>` (standard)
- Legacy: `X-LV3-Dify-Api-Key` (preserved for backward compatibility)

---

## Consequences

**Positive:**
- **Swappable runtime:** Moving to a different agent provider requires writing
  one new adapter (implementing 6 methods), not refactoring the entire platform.
- **Testable in isolation:** The stub provider enables unit and integration
  tests without a running LibreChat instance.
- **Clear contracts:** DTOs make the agent interface explicit and documented,
  reducing tribal knowledge.
- **Multi-provider future:** Nothing prevents running multiple providers
  simultaneously (e.g., LibreChat for conversational agents, a lightweight
  custom runtime for batch operations).
- **Clean tool-naming migration:** The `/v1/tools/` alias removes the
  confusing Dify branding without breaking existing consumers.

**Negative / Trade-offs:**
- **Upfront abstraction cost:** Writing the adapter layer before we actually
  need a second provider is speculative. Justified because:
  (a) we have already migrated from Dify to LibreChat once, proving the
  risk is real; (b) the abstraction is thin (6 methods, ~200 lines per
  adapter) and unlikely to become a maintenance burden.
- **Feature lag:** Provider-specific features (e.g., LibreChat's artifact
  rendering, Open Responses semantic events) must be exposed through the
  DTO layer or accessed via provider-specific escape hatches. We accept
  that the DTO covers the 90% case; provider-specific features use
  `metadata` dict pass-through.
- **Two paths during migration:** Until all consumers are migrated, both
  direct-to-LibreChat and DTO-based paths coexist. The migration plan
  above defines the order.

---

## Related

- ADR 0394 — LibreChat Agents API Integration (depends on this abstraction)
- ADR 0373 — Derive Service Defaults / Inversion of Control (same DI principle applied to service config)
- ADR 0359 — Declarative PostgreSQL Registry (prior example of replacing N implementations with one contract)
- `config/agent-tool-registry.json` — Already-decoupled tool definitions
- `platform/interface_contracts.py` — Existing contract validation patterns
