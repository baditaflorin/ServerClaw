# ADR 0069: Agent Tool Registry And Governed Tool Calls

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.61.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-22
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

- `controller_local` — repo-local script or catalog-backed call on the controller for repo-grounded observe, report, approval, and bounded execution flows
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

## Implementation Notes

- [config/agent-tool-registry.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/agent-tool-registry.json) is now the canonical machine-readable registry for governed `observe`, `report`, `execute`, and `approve` tools.
- [docs/schema/agent-tool.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/agent-tool.json), [docs/schema/agent-tool-registry.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/agent-tool-registry.json), and [docs/schema/governed-tool-call-audit-event.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/governed-tool-call-audit-event.json) now define the registry and audit event contract.
- [scripts/agent_tool_registry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/agent_tool_registry.py) validates the registry, exports MCP-compatible tool definitions, dispatches bounded controller-local tool calls, and emits one audit event for every tool call to `.local/tool-audit/agent-tool-calls.jsonl` by default.
- [Makefile](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/Makefile) now exposes `make agent-tools`, `make agent-tool-info TOOL=<name>`, and `make export-mcp-tools` as the preferred operator entry points.
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py) now fails validation if the governed tool registry drifts from its schema or references missing workflow, command, or API publication entries.
- [docs/runbooks/agent-tool-registry.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/agent-tool-registry.md) records the operating procedure for discovery, MCP export, audit-log location, and governed command dispatch.
- ADR 0070 extends the governed surface with `query-platform-context`, an authenticated `http` observe tool backed by the private platform-context API on the operator-only API lane.
