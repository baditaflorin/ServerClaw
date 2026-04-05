# Container Operations

## Purpose

This runbook covers the agent-facing tools for inspecting Docker containers and their logs across the platform via Portainer.

## Tools

### list-containers

Lists all running Docker containers visible to the platform Portainer instance.

**Transport:** `controller_local` (calls the API gateway handler which queries Portainer)

**Parameters:**
- `include_stopped` (boolean, optional, default: false) — set to true to include stopped/exited containers

**Returns:** `{ count, containers: [{ id, names, image, state, status }] }`

### get-container-logs

Retrieves the tail of stdout/stderr logs for a named container.

**Transport:** `controller_local`

**Parameters:**
- `container` (string, required) — container name, ID prefix, or partial name
- `tail` (integer, optional, default: 100) — number of log lines to return

**Returns:** `{ container, tail, logs }`

## Canonical Sources

- tool registry: [config/agent-tool-registry.json](../../config/agent-tool-registry.json)
- handler: [scripts/agent_tool_registry.py](../../scripts/agent_tool_registry.py) (`tool_list_containers`, `tool_get_container_logs`)
- Portainer client: [scripts/portainer_tool.py](../../scripts/portainer_tool.py)
- API gateway env vars: `LV3_PORTAINER_BASE_URL`, `LV3_PORTAINER_USERNAME`, `LV3_PORTAINER_PASSWORD`, `LV3_PORTAINER_ENDPOINT_ID`

## Prerequisites

The API gateway must have valid Portainer credentials in its environment (set via `api_gateway_portainer_admin_password_local_file` in the `api_gateway_runtime` role).
