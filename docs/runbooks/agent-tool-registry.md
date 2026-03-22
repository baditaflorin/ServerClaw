# Agent Tool Registry

## Purpose

This runbook documents the canonical agent tool registry introduced by ADR 0069.

The registry is the machine-readable discovery layer for governed read and execute surfaces. It does not replace the workflow catalog, command catalog, or private API publication model.

## Canonical Files

- `config/agent-tool-registry.json`
- `docs/schema/agent-tool.json`
- `scripts/agent_tool_registry.py`

## Commands

Inspect the registered tools:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/agent_tool_registry.py --list
```

Inspect one tool definition:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/agent_tool_registry.py --tool query-platform-context
```

Validate the registry:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uvx --from pyyaml python scripts/agent_tool_registry.py --validate
```

Export MCP-compatible tool definitions:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make export-mcp-tools
```

## Operating Notes

- `http` tools must point at a documented API lane surface from `config/control-plane-lanes.json`.
- `execute` tools stay aligned with the workflow catalog and command catalog; approval policy still comes from the command contract, not from chat context.
- The first registry intentionally favors read-heavy tools. `query-platform-context` is the main grounded retrieval surface, while execute-category tools reference governed converge workflows rather than broad shell access.
