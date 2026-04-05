# ADR 0369: Agent Service API Gateway — Governed Pattern for Internal Service Tools

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.19
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-06
- Date: 2026-04-06
- Tags: agents, tools, api, governance, credentials, pattern

## Context

The agent tool registry (ADR 0069) defines a framework for named, governed,
auditable tools that agents can call. Several internal platform services already
have REST API clients in the repository:

- **PlaneClient** (`platform/ansible/plane.py`) — full REST wrapper for Plane
  task management with issue CRUD, comments, labels, and state management
- **OutlineClient** (`scripts/outline_client.py`) — REST wrapper for the Outline
  wiki with document and collection operations
- Nomad, Portainer, and the platform-context API already have ad-hoc tool
  integrations in `scripts/agent_tool_registry.py`

The Nomad tools added in ADR 0368 established a working pattern but did not
formalize it. Each new service integration re-invents credential discovery,
client construction, error handling, and governance classification. As the
number of internal services grows (Dify, Netbox, Keycloak admin, Woodpecker),
this ad-hoc approach leads to inconsistent security posture and duplicated
boilerplate.

What is missing is a documented, repeatable pattern that answers:

1. How does a tool handler discover credentials for a service?
2. How is a service REST client constructed within a handler?
3. Which governance category applies to which API operations?
4. How are service-specific constants (workspace slug, project ID) resolved?
5. What is the standard error shape when a service API call fails?

## Decision

### 1. Credential discovery convention

All agent-callable service tools discover credentials from the `.local/`
directory tree using this precedence:

1. **Environment variable override** — `LV3_<SERVICE>_AUTH_FILE` or
   `LV3_<SERVICE>_API_TOKEN_FILE` (for CI, testing, or multi-instance setups)
2. **Structured auth file** — `.local/<service>/admin-auth.json` containing
   `base_url`, `api_token`, and optional service-specific fields (workspace_slug,
   project_id, verify_ssl)
3. **Plain token file** — `.local/<service>/api-token.txt` containing a single
   API token string, combined with a base URL from the service topology or a
   well-known default constant

A shared helper `_resolve_service_auth(service_name)` centralises this
logic in `scripts/agent_tool_registry.py`. It returns a dict with at minimum
`{"base_url": str, "api_token": str}`.

### 2. Client construction pattern

Each service defines a private `_<service>_client()` factory function in
`agent_tool_registry.py` that:

- Calls `_resolve_service_auth(service_name)` for credentials
- Lazy-imports the service client class (same pattern as `import requests`
  in the Nomad handler)
- Constructs the client with the resolved auth
- Does NOT cache the client across calls (stateless per-invocation, safe for
  token rotation)

### 3. Service context resolution

Service-specific constants (Plane workspace slug, Outline collection ID) are
stored in the structured auth file alongside credentials. The auth file is the
single source of truth for "which instance and which scope does this tool
operate on."

### 4. Governance classification for service API tools

| API operation type | Tool category | approval_required | MCP annotations |
|---|---|---|---|
| List / get / search (read-only) | `observe` | `false` | readOnlyHint: true, idempotentHint: true |
| Create | `execute` | `true` | destructiveHint: false, openWorldHint: true |
| Update / transition | `execute` | `false` | destructiveHint: false, openWorldHint: true |
| Delete / archive | `execute` | `true` | destructiveHint: true, openWorldHint: true |
| Add comment / annotation | `execute` | `false` | destructiveHint: false, openWorldHint: true |

The `approval_required` flag controls whether the agent runtime must obtain
human confirmation before dispatching. Create operations default to
`approval_required: true` because they produce persistent external state.
Update and comment operations default to `false` because agents frequently
need to update their own task status without blocking on human approval.

Individual service ADRs may override these defaults with justification.

### 5. Standard error handling

When a service API call fails, the handler raises an exception. The
`call_tool` dispatcher in `agent_tool_registry.py` already catches all
exceptions and returns a structured error response with `isError: true`.
Service handlers MUST NOT swallow exceptions.

### 6. Tool naming convention

Service tools follow the pattern `<verb>-<service>-<noun>`:

- `list-plane-tasks`, `create-plane-task`, `get-plane-task`
- `list-outline-documents`, `search-outline-documents`
- `list-nomad-jobs`, `dispatch-nomad-job`

The service name is always a single word matching the `.local/<service>/`
directory name.

## Consequences

### Positive

- New service integrations follow a documented, reviewable pattern
- Credential management is consistent across all services
- Governance classification is predictable and auditable
- The pattern scales to any REST API service without framework changes

### Negative / Trade-offs

- The structured auth file convention means credentials are stored as
  plaintext JSON on the controller; acceptable for the current single-operator
  model but should migrate to OpenBao when that matures
- Per-invocation client construction adds ~1ms vs. a cached client;
  negligible for API calls taking 50-500ms
- The pattern is REST-centric; gRPC or WebSocket services would need a
  variant (out of scope)

## Related ADRs

- ADR 0069: Agent tool registry and governed tool calls (framework)
- ADR 0368: Nomad OIDC and agent tools (first service API tools, ad-hoc)
- ADR 0360: Plane as Agent Task HQ (Plane integration context)
- ADR 0370: Plane agent tools (first formal implementation of this pattern)
