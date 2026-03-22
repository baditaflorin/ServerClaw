# ADR 0069: Agent Tool Registry And Governed Tool Calls

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Agents interacting with this platform currently have two options:

1. read static files (ADRs, runbooks, receipts, `stack.yaml`) — safe but limited to committed state
2. execute arbitrary shell commands via SSH — powerful but ungoverned and difficult to audit

What is missing is a middle layer: named, documented, parameterised tools that an agent can call with known inputs and outputs, subject to the same approval gates and audit trail as the command catalog (ADR 0048).

The command catalog covers mutating commands. The workflow catalog covers Windmill workflows. Neither is structured as a callable tool registry that an agent can discover, understand, and invoke programmatically without reading multiple JSON files and runbooks.

## Decision

We will define an agent tool registry as a machine-readable catalog of named tools available to agents and operators.

Registry structure (`config/agent-tool-registry.json`):

```json
{
  "tools": [
    {
      "name": "get-platform-status",
      "description": "Return current platform health summary from Uptime Kuma and Grafana",
      "category": "observe",
      "input_schema": {},
      "output_schema": { "type": "object" },
      "transport": "http",
      "endpoint": "internal",
      "auth": "openbao-token",
      "approval_required": false,
      "audit_on_call": true
    }
  ]
}
```

Tool categories:

- **observe** — read-only queries against live platform state (health, metrics, topology, logs)
- **report** — generate structured documents (status docs, drift summaries, receipt listings)
- **execute** — trigger an approved workflow or command with arguments
- **approve** — submit or confirm an approval gate for a pending mutation

Tool transport options:

- `http` — REST or GraphQL call to an internal API (Windmill, NetBox, Grafana)
- `nats` — publish a request event and receive a reply
- `ansible` — invoke a named Ansible workflow via the workflow catalog

MCP compatibility: the registry schema is compatible with the Model Context Protocol tool-use format so agents running on MCP-capable runtimes (e.g. Claude Code, Open WebUI) can load the registry and call tools natively.

## Consequences

- Agents gain a self-describing capability surface without needing direct shell access.
- New tools are reviewed and catalogued before agents can use them, preventing scope creep.
- Every tool call emits a mutation audit event (ADR 0066) regardless of whether it mutates or only reads.
- The registry must be kept current as services are added or their APIs change.

## Boundaries

- The tool registry does not replace the command catalog or workflow catalog; it is the discovery and dispatch layer on top of them.
- Tools that require break-glass access are not listed in the public registry; they are documented separately in the break-glass runbook.
- Agent-to-agent tool calls are out of scope for the first iteration.
