#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from command_catalog import load_command_catalog
from control_plane_lanes import load_lane_catalog, require_identifier
from controller_automation_toolkit import REPO_ROOT, emit_cli_error, load_json, repo_path
from workflow_catalog import load_workflow_catalog


REGISTRY_PATH = repo_path("config", "agent-tool-registry.json")
SUPPORTED_SCHEMA_VERSION = "1.0.0"
ALLOWED_CATEGORIES = {"observe", "report", "execute", "approve"}
ALLOWED_TRANSPORTS = {"http", "nats", "ansible"}
HTTP_METHODS = {"GET", "POST"}


def require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return value


def require_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def require_schema(value: Any, path: str) -> dict[str, Any]:
    schema = require_mapping(value, path)
    require_str(schema.get("type"), f"{path}.type")
    return schema


def load_registry() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    catalog = require_mapping(load_json(REGISTRY_PATH), str(REGISTRY_PATH))
    normalized_tools = validate_registry(catalog)
    return catalog, normalized_tools


def validate_registry(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    schema_version = require_str(catalog.get("schema_version"), "agent-tool-registry.schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"agent-tool-registry.schema_version must be '{SUPPORTED_SCHEMA_VERSION}'"
        )

    workflow_ids = set(load_workflow_catalog()["workflows"].keys())
    command_ids = set(load_command_catalog()["commands"].keys())
    _lane_catalog, normalized_lanes = load_lane_catalog()
    api_surface_ids = {
        surface["id"]
        for surface in normalized_lanes["api"]["current_surfaces"]
    }

    tools = require_list(catalog.get("tools"), "agent-tool-registry.tools")
    if len(tools) < 5:
        raise ValueError("agent-tool-registry.tools must define at least five tools")

    names: set[str] = set()
    categories_in_use: set[str] = set()
    normalized_tools: list[dict[str, Any]] = []
    for index, tool in enumerate(tools):
        path = f"agent-tool-registry.tools[{index}]"
        tool = require_mapping(tool, path)
        name = require_identifier(tool.get("name"), f"{path}.name")
        if name in names:
            raise ValueError(f"duplicate agent tool name '{name}'")
        names.add(name)

        category = require_str(tool.get("category"), f"{path}.category")
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"{path}.category must be one of {sorted(ALLOWED_CATEGORIES)}")
        categories_in_use.add(category)

        transport = require_str(tool.get("transport"), f"{path}.transport")
        if transport not in ALLOWED_TRANSPORTS:
            raise ValueError(f"{path}.transport must be one of {sorted(ALLOWED_TRANSPORTS)}")

        description = require_str(tool.get("description"), f"{path}.description")
        auth = require_str(tool.get("auth"), f"{path}.auth")
        approval_required = require_bool(tool.get("approval_required"), f"{path}.approval_required")
        audit_on_call = require_bool(tool.get("audit_on_call"), f"{path}.audit_on_call")
        input_schema = require_schema(tool.get("input_schema"), f"{path}.input_schema")
        output_schema = require_schema(tool.get("output_schema"), f"{path}.output_schema")

        normalized_tool = {
            "name": name,
            "category": category,
            "transport": transport,
            "description": description,
            "auth": auth,
            "approval_required": approval_required,
            "audit_on_call": audit_on_call,
            "input_schema": input_schema,
            "output_schema": output_schema,
        }

        if transport == "http":
            http = require_mapping(tool.get("http"), f"{path}.http")
            api_surface_ref = require_identifier(http.get("api_surface_ref"), f"{path}.http.api_surface_ref")
            if api_surface_ref not in api_surface_ids:
                raise ValueError(f"{path}.http.api_surface_ref references unknown API surface '{api_surface_ref}'")
            method = require_str(http.get("method"), f"{path}.http.method").upper()
            if method not in HTTP_METHODS:
                raise ValueError(f"{path}.http.method must be one of {sorted(HTTP_METHODS)}")
            http_path = require_str(http.get("path"), f"{path}.http.path")
            if not http_path.startswith("/"):
                raise ValueError(f"{path}.http.path must start with '/'")
            normalized_tool["http"] = {
                "api_surface_ref": api_surface_ref,
                "method": method,
                "path": http_path,
            }

        if transport == "ansible":
            ansible = require_mapping(tool.get("ansible"), f"{path}.ansible")
            workflow_id = require_identifier(ansible.get("workflow_id"), f"{path}.ansible.workflow_id")
            if workflow_id not in workflow_ids:
                raise ValueError(f"{path}.ansible.workflow_id references unknown workflow '{workflow_id}'")
            if category != "execute":
                raise ValueError(f"{path} ansible tools must use the 'execute' category")
            normalized_tool["ansible"] = {"workflow_id": workflow_id}

        if transport == "nats":
            nats = require_mapping(tool.get("nats"), f"{path}.nats")
            subject = require_str(nats.get("subject"), f"{path}.nats.subject")
            normalized_tool["nats"] = {"subject": subject}

        command_ref = tool.get("command_ref")
        if command_ref is not None:
            command_ref = require_identifier(command_ref, f"{path}.command_ref")
            if command_ref not in command_ids:
                raise ValueError(f"{path}.command_ref references unknown command '{command_ref}'")
            normalized_tool["command_ref"] = command_ref

        normalized_tools.append(normalized_tool)

    if not {"observe", "report", "execute"}.issubset(categories_in_use):
        raise ValueError("agent-tool-registry.tools must cover observe, report, and execute categories")

    return normalized_tools


def list_tools(tools: list[dict[str, Any]]) -> int:
    print(f"Agent tool registry: {REGISTRY_PATH}")
    for tool in tools:
        print(f"  - {tool['name']} [{tool['category']}, {tool['transport']}]")
    return 0


def show_tool(tools: list[dict[str, Any]], tool_name: str) -> int:
    tool = next((item for item in tools if item["name"] == tool_name), None)
    if tool is None:
        print(f"Unknown agent tool: {tool_name}", file=sys.stderr)
        return 2
    print(json.dumps(tool, indent=2, sort_keys=True))
    return 0


def export_mcp(tools: list[dict[str, Any]], output_path: Path | None) -> int:
    payload = {
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["input_schema"],
                "annotations": {
                    "readOnlyHint": tool["category"] in {"observe", "report"},
                },
            }
            for tool in tools
        ]
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        sys.stdout.write(rendered)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or validate the canonical agent tool registry.")
    parser.add_argument("--list", action="store_true", help="List registered tools.")
    parser.add_argument("--tool", help="Show one tool definition.")
    parser.add_argument("--validate", action="store_true", help="Validate the registry.")
    parser.add_argument("--export-mcp", action="store_true", help="Export registry entries as MCP-style tool definitions.")
    parser.add_argument("--output", help="Optional output path for --export-mcp.")
    args = parser.parse_args()

    try:
        _catalog, tools = load_registry()
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        return emit_cli_error("Agent tool registry", exc)

    if args.validate:
        print(f"Agent tool registry OK: {REGISTRY_PATH}")
        return 0
    if args.tool:
        return show_tool(tools, args.tool)
    if args.export_mcp:
        output_path = Path(args.output).expanduser() if args.output else None
        return export_mcp(tools, output_path)
    return list_tools(tools)


if __name__ == "__main__":
    sys.exit(main())
