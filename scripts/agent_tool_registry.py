#!/usr/bin/env python3

import argparse
import json
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, repo_path


AGENT_TOOL_REGISTRY_PATH = repo_path("config", "agent-tool-registry.json")
WORKFLOW_CATALOG_PATH = repo_path("config", "workflow-catalog.json")
COMMAND_CATALOG_PATH = repo_path("config", "command-catalog.json")

ALLOWED_CATEGORIES = {"observe", "report", "execute", "approve"}
ALLOWED_TRANSPORTS = {"http", "nats", "ansible"}


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


def load_agent_tool_registry() -> dict[str, Any]:
    return load_json(AGENT_TOOL_REGISTRY_PATH)


def validate_agent_tool_registry(registry: dict[str, Any]) -> None:
    if registry.get("schema_version") != "1.0.0":
        raise ValueError("agent tool registry must declare schema_version '1.0.0'")

    workflow_catalog = load_json(WORKFLOW_CATALOG_PATH)
    command_catalog = load_json(COMMAND_CATALOG_PATH)
    known_make_targets = {
        workflow["preferred_entrypoint"]["target"]
        for workflow in workflow_catalog["workflows"].values()
        if workflow["preferred_entrypoint"]["kind"] == "make_target"
    }
    known_make_targets.update(command_catalog["commands"].keys())

    tools = require_list(registry.get("tools"), "tools")
    if len(tools) < 5:
        raise ValueError("agent tool registry must define at least 5 tools")

    seen_names: set[str] = set()
    for index, tool in enumerate(tools):
        tool = require_mapping(tool, f"tools[{index}]")
        name = require_str(tool.get("name"), f"tools[{index}].name")
        if name in seen_names:
            raise ValueError(f"duplicate tool name: {name}")
        seen_names.add(name)

        require_str(tool.get("description"), f"tools[{index}].description")
        category = require_str(tool.get("category"), f"tools[{index}].category")
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"tools[{index}].category must be one of {sorted(ALLOWED_CATEGORIES)}")

        transport = require_str(tool.get("transport"), f"tools[{index}].transport")
        if transport not in ALLOWED_TRANSPORTS:
            raise ValueError(
                f"tools[{index}].transport must be one of {sorted(ALLOWED_TRANSPORTS)}"
            )

        require_bool(tool.get("approval_required"), f"tools[{index}].approval_required")
        require_bool(tool.get("audit_on_call"), f"tools[{index}].audit_on_call")
        require_mapping(tool.get("input_schema"), f"tools[{index}].input_schema")
        require_mapping(tool.get("output_schema"), f"tools[{index}].output_schema")
        endpoint = require_str(tool.get("endpoint"), f"tools[{index}].endpoint")

        if transport == "ansible" and endpoint.startswith("make "):
            target = endpoint.split()[1]
            if "<" in target:
                continue
            if target not in known_make_targets and target != "generate-ops-portal":
                raise ValueError(f"tools[{index}].endpoint references unknown make target '{target}'")


def export_mcp_tools(registry: dict[str, Any]) -> int:
    payload = []
    for tool in registry["tools"]:
        payload.append(
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["input_schema"],
                "annotations": {
                    "category": tool["category"],
                    "transport": tool["transport"],
                    "approval_required": tool["approval_required"],
                    "audit_on_call": tool["audit_on_call"],
                },
            }
        )
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or export the agent tool registry.")
    parser.add_argument("--validate", action="store_true", help="Validate and exit.")
    parser.add_argument("--export-mcp", action="store_true", help="Export MCP-compatible tool JSON.")
    args = parser.parse_args(argv)

    try:
        registry = load_agent_tool_registry()
        validate_agent_tool_registry(registry)
        if args.export_mcp:
            return export_mcp_tools(registry)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("agent tool registry", exc)


if __name__ == "__main__":
    raise SystemExit(main())
