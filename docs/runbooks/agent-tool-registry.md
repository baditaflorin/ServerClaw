# Agent Tool Registry

## Purpose

This runbook defines the canonical governed tool registry for agents and operators.

The registry adds a self-describing tool surface on top of the existing workflow, command, receipt, and publication catalogs so agents do not need broad shell access just to discover or call approved operations.

## Canonical Sources

- tool registry: [config/agent-tool-registry.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/agent-tool-registry.json)
- tool schema: [docs/schema/agent-tool.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/agent-tool.json)
- registry schema: [docs/schema/agent-tool-registry.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/agent-tool-registry.json)
- audit event schema: [docs/schema/governed-tool-call-audit-event.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/governed-tool-call-audit-event.json)
- registry CLI: [scripts/agent_tool_registry.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/agent_tool_registry.py)
- workflow catalog: [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json)
- command catalog: [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json)
- API publication catalog: [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/api-publication.json)

## Current Transport Model

The first implementation adds one bounded transport in addition to the ADR’s planned live transports:

- `controller_local`: repo-local script and catalog-backed calls on the controller for repo-grounded observe, report, approval, and governed command dispatch
- `http`, `nats`, and `ansible` remain valid registry values for future live-backed tool entries

This keeps the first tool surface useful immediately without pretending that every future live API and event surface already exists.

## Primary Commands

List the governed tools:

```bash
make agent-tools
```

Show one tool contract:

```bash
make agent-tool-info TOOL=get-platform-status
```

Validate the registry directly:

```bash
scripts/agent_tool_registry.py --validate
```

Export the MCP-compatible tool definitions:

```bash
make export-mcp-tools > /tmp/lv3-mcp-tools.json
```

Call a read-only observe tool:

```bash
uvx --from pyyaml python scripts/agent_tool_registry.py \
  --call get-platform-status \
  --args-json '{}'
```

Evaluate a command approval gate:

```bash
scripts/agent_tool_registry.py \
  --call check-command-approval \
  --args-json '{"command_id":"configure-network","requester_class":"human_operator","approver_classes":["human_operator"],"preflight_passed":true,"validation_passed":true,"receipt_planned":true}'
```

Prepare a governed command execution without actually running it:

```bash
scripts/agent_tool_registry.py \
  --call run-governed-command \
  --args-json '{"command_id":"configure-network","requester_class":"human_operator","approver_classes":["human_operator"],"preflight_passed":true,"validation_passed":true,"receipt_planned":true,"dry_run":true}'
```

## Audit Events

Every tool call appends one governed-tool-call audit event to the controller-local JSON-lines stream:

- default path: `.local/tool-audit/agent-tool-calls.jsonl`
- override path: set `LV3_AGENT_TOOL_AUDIT_LOG_PATH=/absolute/path/to/file.jsonl`

This is the bounded ADR 0069 tool-call audit stream. It does not claim to replace the broader multi-surface mutation audit work planned under ADR 0066.

## Operating Rule

When adding or changing a governed tool:

1. update [config/agent-tool-registry.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/agent-tool-registry.json)
2. keep the input and output schemas MCP-compatible
3. cross-reference the owning workflow, command, or API publication surface where applicable
4. keep `audit_on_call` enabled
5. rerun `scripts/agent_tool_registry.py --validate`
6. rerun `make export-mcp-tools`
7. rerun `make validate`

If a recurring agent action is not represented in the tool registry, it is not yet an approved governed tool surface.
