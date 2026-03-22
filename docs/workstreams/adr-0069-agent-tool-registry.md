# Workstream ADR 0069: Agent Tool Registry And Governed Tool Calls

- ADR: [ADR 0069](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0069-agent-tool-registry-and-governed-tool-calls.md)
- Title: Self-describing, MCP-compatible tool catalog for agents and operators
- Status: ready
- Branch: `codex/adr-0069-agent-tool-registry`
- Worktree: `../proxmox_florin_server-agent-tool-registry`
- Owner: codex
- Depends On: `adr-0048-command-catalog`, `adr-0049-private-api-publication`, `adr-0058-nats-event-bus`, `adr-0066-mutation-audit-log`
- Conflicts With: none
- Shared Surfaces: `config/`, `config/command-catalog.json`, `config/workflow-catalog.json`, Open WebUI tool definitions

## Scope

- define `config/agent-tool-registry.json` schema and initial tool set
- populate the registry with `observe`, `report`, and `execute` category tools backed by existing surfaces
- validate the registry schema in `make validate`
- document tool usage in `docs/runbooks/agent-tool-registry.md`
- provide an MCP-compatible JSON export via `make export-mcp-tools`

## Non-Goals

- agent-to-agent tool calls in this iteration
- break-glass tools

## Expected Repo Surfaces

- `config/agent-tool-registry.json`
- `docs/schema/agent-tool.json` (JSON Schema for individual tool entries)
- `docs/runbooks/agent-tool-registry.md`
- updated `Makefile` with `export-mcp-tools` target
- `docs/adr/0069-agent-tool-registry-and-governed-tool-calls.md`
- `docs/workstreams/adr-0069-agent-tool-registry.md`
- `workstreams.yaml`

## Expected Live Surfaces

- agents can load the registry and call `observe` category tools immediately
- `execute` category tools require approval gate before execution

## Verification

- `python3 -c "import json; json.load(open('config/agent-tool-registry.json'))"` exits 0
- `make export-mcp-tools` produces valid MCP tool definitions
- at least one `observe` tool can be called end-to-end from an agent context

## Merge Criteria

- the registry schema is valid JSON Schema
- at least 5 tools are defined covering all three initial categories
- MCP export passes schema validation
- the audit event is emitted on every tool call in the test run

## Notes For The Next Assistant

- seed the initial tool set from existing workflow-catalog and command-catalog entries where the transport already exists
- prioritise `get-platform-status` and `list-recent-receipts` as the first `observe` tools since they have no side effects
