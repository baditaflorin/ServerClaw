# ADR 0364: Outline Agent Tools — Programmatic Wiki Access for Agents

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.22
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-06
- Date: 2026-04-06
- Tags: agents, tools, outline, wiki, api, automation

## Context

ADR 0362 established the Agent Service API Gateway pattern. ADR 0363 implemented
it for Plane (task management). The Outline wiki at `wiki.example.com` is the platform
knowledge base — runbooks, ADRs, workstream docs, and operational findings all live
there. An existing REST client (`scripts/outline_client.py`) already wraps the API.

Currently agents can only read the Outline wiki by navigating to URLs directly. They
cannot search documents, retrieve full content, or create new documents
programmatically through the governed tool registry.

The immediate use cases:
- An agent working on a service reads the relevant runbook before making changes
- An agent writes a post-incident finding as a wiki document
- An agent searches for prior art before designing a new ADR

## Decision

### Tools added to the agent tool registry

Four Outline tools following the ADR 0362 gateway pattern:

| Tool name | Category | approval_required | Outline API endpoint |
|---|---|---|---|
| `list-outline-collections` | observe | false | `collections.list` |
| `search-outline-documents` | observe | false | `documents.search` |
| `get-outline-document` | observe | false | `documents.info` |
| `create-outline-document` | execute | true | `documents.create` |

### list-outline-collections (observe)

List all collections in the workspace.

- Input: none
- Output: `{count, collections: [{id, name, description, documents_count}]}`

### search-outline-documents (observe)

Full-text search with optional collection scope.

- Input: `query` (required), `collection_id` (optional), `limit` (default 25)
- Output: `{count, query, results: [{id, title, collection_id, url, ranking}]}`

### get-outline-document (observe)

Retrieve full document content by UUID.

- Input: `document_id` (required)
- Output: `{id, title, text, collection_id, url, created_at, updated_at}`

### create-outline-document (execute, approval_required)

Create a new published document in a collection.

- Input: `title` (required), `collection_id` (required), `text` (Markdown),
  `parent_document_id` (optional, for nesting), `publish` (default true)
- Output: `{id, title, url, collection_id}`

### Credential resolution

Following ADR 0362 `_resolve_service_auth("outline")` precedence:

1. Env var `LV3_OUTLINE_AUTH_FILE` → structured auth JSON
2. `.local/outline/admin-auth.json` → `{base_url, api_token}`
3. `.local/outline/api-token.txt` → single token; `base_url` defaults to `https://wiki.example.com`

The existing `.local/outline/api-token.txt` has limited scope (only publicly accessible
endpoints like `collections.list` work without auth). For full API access, create
`.local/outline/admin-auth.json`:

```json
{
  "base_url": "https://wiki.example.com",
  "api_token": "<token from Outline Settings → API → Personal access token>"
}
```

Once `admin-auth.json` is present, `_resolve_service_auth("outline")` will prefer it
over `api-token.txt`.

### Client construction

`_outline_client()` in `scripts/agent_tool_registry.py` lazy-imports
`OutlineClient` from `scripts/outline_client.py` and constructs it with the
resolved auth. Stateless per-invocation per ADR 0362.

## Consequences

### Positive

- Agents can now search the wiki before starting work, reducing duplicate effort
- Agents can write findings, runbooks, and post-incident docs directly
- Reuses the existing `OutlineClient` — no new HTTP wiring
- `_resolve_service_auth("outline")` delegates to the generic ADR 0362 helper

### Negative / Trade-offs

- `create-outline-document` requires human approval; intentional for first iteration
- No `update-outline-document` or `delete-outline-document` tools yet — can be added
  following the same pattern once the need arises
- The Outline API uses POST for all operations including reads; this is correct
  Outline API behaviour, not a registry misconfiguration

## Related ADRs

- ADR 0362: Agent Service API Gateway pattern (generic credential/client pattern)
- ADR 0363: Plane agent tools (prior art for this implementation)
- ADR 0069: Agent tool registry and governed tool calls
