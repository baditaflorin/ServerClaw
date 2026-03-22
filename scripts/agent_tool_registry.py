#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

from api_publication import load_api_publication_catalog
from command_catalog import (
    ALLOWED_IDENTITY_CLASSES,
    evaluate_approval,
    load_command_catalog,
    validate_command_catalog,
)
from controller_automation_toolkit import REPO_ROOT, emit_cli_error, load_json, load_yaml, repo_path
from live_apply_receipts import iter_receipt_paths, load_receipt, validate_receipts
from workflow_catalog import (
    load_secret_manifest,
    load_workflow_catalog,
    validate_secret_manifest,
    validate_workflow_catalog,
)


AGENT_TOOL_REGISTRY_PATH: Final[Path] = repo_path("config", "agent-tool-registry.json")
TOOL_SCHEMA_PATH: Final[Path] = repo_path("docs", "schema", "agent-tool.json")
REGISTRY_SCHEMA_PATH: Final[Path] = repo_path("docs", "schema", "agent-tool-registry.json")
AUDIT_SCHEMA_PATH: Final[Path] = repo_path("docs", "schema", "governed-tool-call-audit-event.json")
STACK_PATH: Final[Path] = repo_path("versions", "stack.yaml")
HOST_VARS_PATH: Final[Path] = repo_path("inventory", "host_vars", "proxmox_florin.yml")
AUDIT_LOG_ENV: Final[str] = "LV3_AGENT_TOOL_AUDIT_LOG_PATH"
PLATFORM_CONTEXT_TOKEN_ENV: Final[str] = "LV3_PLATFORM_CONTEXT_API_TOKEN_FILE"
DEFAULT_PLATFORM_CONTEXT_TOKEN_PATH: Final[Path] = REPO_ROOT / ".local" / "platform-context" / "api-token.txt"
SUPPORTED_SCHEMA_VERSION: Final[str] = "1.0.0"
ALLOWED_TOOL_CATEGORIES: Final[set[str]] = {"observe", "report", "execute", "approve"}
ALLOWED_TRANSPORTS: Final[set[str]] = {"controller_local", "http", "nats", "ansible"}


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


def require_int(value: Any, path: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{path} must be >= {minimum}")
    return value


def validate_json_schema_shape(
    schema: Any,
    path: str,
    *,
    require_meta: bool = False,
) -> dict[str, Any]:
    schema = require_mapping(schema, path)
    if require_meta:
        require_str(schema.get("$schema"), f"{path}.$schema")
    if "title" in schema:
        require_str(schema.get("title"), f"{path}.title")
    schema_type = schema.get("type")
    if schema_type is not None and schema_type not in {"object", "array", "string", "integer", "boolean"}:
        raise ValueError(f"{path}.type uses unsupported schema type '{schema_type}'")
    if "properties" in schema:
        properties = require_mapping(schema.get("properties"), f"{path}.properties")
        for key, value in properties.items():
            require_str(key, f"{path}.properties key")
            validate_json_schema_shape(value, f"{path}.properties.{key}")
    if "items" in schema:
        validate_json_schema_shape(schema.get("items"), f"{path}.items")
    if "required" in schema:
        for index, value in enumerate(require_list(schema.get("required"), f"{path}.required")):
            require_str(value, f"{path}.required[{index}]")
    if "enum" in schema:
        require_list(schema.get("enum"), f"{path}.enum")
    if "const" in schema:
        pass
    if "additionalProperties" in schema and not isinstance(schema.get("additionalProperties"), bool):
        raise ValueError(f"{path}.additionalProperties must be boolean when present")
    return schema


def validate_instance(instance: Any, schema: dict[str, Any], path: str) -> None:
    if "const" in schema and instance != schema["const"]:
        raise ValueError(f"{path} must equal {schema['const']!r}")

    schema_type = schema.get("type")
    if schema_type == "object":
        obj = require_mapping(instance, path)
        properties = require_mapping(schema.get("properties", {}), f"{path} schema.properties")
        required = set(schema.get("required", []))
        for key in required:
            if key not in obj:
                raise ValueError(f"{path}.{key} is required")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(obj.keys()) - set(properties.keys()))
            if extras:
                raise ValueError(f"{path} contains unsupported properties: {', '.join(extras)}")
        for key, value in obj.items():
            if key in properties:
                validate_instance(value, properties[key], f"{path}.{key}")
        return

    if schema_type == "array":
        items = require_list(instance, path)
        item_schema = schema.get("items")
        if item_schema is not None:
            item_schema = validate_json_schema_shape(item_schema, f"{path} schema.items")
            for index, value in enumerate(items):
                validate_instance(value, item_schema, f"{path}[{index}]")
        minimum = schema.get("minItems")
        if minimum is not None and len(items) < minimum:
            raise ValueError(f"{path} must contain at least {minimum} item(s)")
        return

    if schema_type == "string":
        value = require_str(instance, path)
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path} must be one of {schema['enum']}")
        return

    if schema_type == "integer":
        value = require_int(instance, path, schema.get("minimum"))
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path} must be one of {schema['enum']}")
        return

    if schema_type == "boolean":
        require_bool(instance, path)
        return

    if "enum" in schema and instance not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}")


def load_registry() -> dict[str, Any]:
    return require_mapping(load_json(AGENT_TOOL_REGISTRY_PATH), str(AGENT_TOOL_REGISTRY_PATH))


def load_agent_tool_registry() -> tuple[dict[str, Any], dict[str, Any]]:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)
    command_catalog = load_command_catalog()
    validate_command_catalog(command_catalog, workflow_catalog, secret_manifest)
    api_surface_ids = load_api_surface_ids()
    registry = load_registry()
    validate_agent_tool_registry(registry, workflow_catalog, command_catalog, api_surface_ids)
    return registry, workflow_catalog


def load_api_surface_ids() -> set[str]:
    catalog = require_mapping(load_json(repo_path("config", "api-publication.json")), "config/api-publication.json")
    surfaces = require_list(catalog.get("surfaces"), "config/api-publication.json.surfaces")
    return {
        require_str(
            require_mapping(surface, f"config/api-publication.json.surfaces[{index}]").get("id"),
            f"config/api-publication.json.surfaces[{index}].id",
        )
        for index, surface in enumerate(surfaces)
    }


def validate_agent_tool_registry(
    registry: dict[str, Any],
    workflow_catalog: dict[str, Any],
    command_catalog: dict[str, Any],
    api_surface_ids: set[str],
) -> None:
    tool_schema = validate_json_schema_shape(load_json(TOOL_SCHEMA_PATH), str(TOOL_SCHEMA_PATH), require_meta=True)
    registry_schema = validate_json_schema_shape(
        load_json(REGISTRY_SCHEMA_PATH), str(REGISTRY_SCHEMA_PATH), require_meta=True
    )
    validate_json_schema_shape(load_json(AUDIT_SCHEMA_PATH), str(AUDIT_SCHEMA_PATH), require_meta=True)
    validate_instance(registry, registry_schema, "agent-tool-registry")

    if registry.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"agent-tool-registry.schema_version must be '{SUPPORTED_SCHEMA_VERSION}'")

    tools = require_list(registry.get("tools"), "agent-tool-registry.tools")
    names: set[str] = set()
    for index, tool in enumerate(tools):
        path = f"agent-tool-registry.tools[{index}]"
        validate_instance(tool, tool_schema, path)
        tool = require_mapping(tool, path)
        name = require_str(tool.get("name"), f"{path}.name")
        if name in names:
            raise ValueError(f"agent-tool-registry defines duplicate tool name '{name}'")
        names.add(name)

        category = require_str(tool.get("category"), f"{path}.category")
        if category not in ALLOWED_TOOL_CATEGORIES:
            raise ValueError(f"{path}.category must be one of {sorted(ALLOWED_TOOL_CATEGORIES)}")
        transport = require_str(tool.get("transport"), f"{path}.transport")
        if transport not in ALLOWED_TRANSPORTS:
            raise ValueError(f"{path}.transport must be one of {sorted(ALLOWED_TRANSPORTS)}")
        if require_bool(tool.get("audit_on_call"), f"{path}.audit_on_call") is not True:
            raise ValueError(f"{path}.audit_on_call must stay true for governed tool calls")

        validate_json_schema_shape(tool.get("input_schema"), f"{path}.input_schema")
        validate_json_schema_shape(tool.get("output_schema"), f"{path}.output_schema")

        implementation = require_mapping(tool.get("implementation"), f"{path}.implementation")
        if require_str(implementation.get("kind"), f"{path}.implementation.kind") != "handler":
            raise ValueError(f"{path}.implementation.kind must stay 'handler' in this iteration")
        require_str(implementation.get("handler"), f"{path}.implementation.handler")

        runbook = REPO_ROOT / require_str(tool.get("runbook"), f"{path}.runbook")
        if not runbook.is_file():
            raise ValueError(f"{path}.runbook references missing file '{tool['runbook']}'")

        catalog_refs = tool.get("catalog_refs", {})
        if catalog_refs:
            catalog_refs = require_mapping(catalog_refs, f"{path}.catalog_refs")
            workflow_id = catalog_refs.get("workflow_id")
            if workflow_id is not None and workflow_id not in workflow_catalog["workflows"]:
                raise ValueError(f"{path}.catalog_refs.workflow_id references unknown workflow '{workflow_id}'")
            command_id = catalog_refs.get("command_id")
            if command_id is not None and command_id not in command_catalog["commands"]:
                raise ValueError(f"{path}.catalog_refs.command_id references unknown command '{command_id}'")
            api_surface_id = catalog_refs.get("api_surface_id")
            if api_surface_id is not None and api_surface_id not in api_surface_ids:
                raise ValueError(
                    f"{path}.catalog_refs.api_surface_id references unknown API surface '{api_surface_id}'"
                )


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def resolve_audit_log_path(registry: dict[str, Any]) -> Path:
    override = os.environ.get(AUDIT_LOG_ENV)
    if override:
        return Path(override).expanduser()
    return REPO_ROOT / require_str(registry.get("default_audit_log_path"), "default_audit_log_path")


def emit_tool_call_audit_event(registry: dict[str, Any], event: dict[str, Any]) -> None:
    schema = validate_json_schema_shape(load_json(AUDIT_SCHEMA_PATH), str(AUDIT_SCHEMA_PATH), require_meta=True)
    validate_instance(event, schema, "governed-tool-call-audit-event")
    path = resolve_audit_log_path(registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def resolve_platform_context_token_path() -> Path:
    override = os.environ.get(PLATFORM_CONTEXT_TOKEN_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_PLATFORM_CONTEXT_TOKEN_PATH


def read_secret_file(path: Path, label: str) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"{label} is empty: {path}")
    return value


def build_tool_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        tool["name"]: tool
        for tool in require_list(registry.get("tools"), "agent-tool-registry.tools")
    }


def render_mcp_tools(registry: dict[str, Any]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for tool in registry["tools"]:
        mcp_tool: dict[str, Any] = {
            "name": tool["name"],
            "title": tool["title"],
            "description": tool["description"],
            "inputSchema": tool["input_schema"],
        }
        if "output_schema" in tool:
            mcp_tool["outputSchema"] = tool["output_schema"]
        if tool.get("mcp_annotations"):
            mcp_tool["annotations"] = tool["mcp_annotations"]
        tools.append(mcp_tool)
    return tools


def load_catalog_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    secret_manifest = load_secret_manifest()
    validate_secret_manifest(secret_manifest)
    workflow_catalog = load_workflow_catalog()
    validate_workflow_catalog(workflow_catalog, secret_manifest)
    command_catalog = load_command_catalog()
    validate_command_catalog(command_catalog, workflow_catalog, secret_manifest)
    return secret_manifest, workflow_catalog, command_catalog


def tool_get_platform_status(_tool: dict[str, Any], _args: dict[str, Any]) -> dict[str, Any]:
    stack = require_mapping(load_yaml(STACK_PATH), str(STACK_PATH))
    host_vars = require_mapping(load_yaml(HOST_VARS_PATH), str(HOST_VARS_PATH))
    topology = require_mapping(host_vars.get("lv3_service_topology"), "host_vars.lv3_service_topology")
    public_services = sorted(
        service["public_hostname"]
        for service in topology.values()
        if isinstance(service, dict) and service.get("public_hostname")
    )
    return {
        "repo_version": normalize_scalar(stack["repo_version"]),
        "platform_version": normalize_scalar(stack["platform_version"]),
        "observed_check_date": normalize_scalar(stack["observed_state"]["checked_at"]),
        "os": stack["observed_state"]["os"],
        "proxmox": stack["observed_state"]["proxmox"],
        "guest_count": len(stack["observed_state"]["guests"]["instances"]),
        "public_services": public_services,
        "latest_receipt_ids": stack["live_apply_evidence"]["latest_receipts"],
    }


def tool_list_recent_receipts(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    validate_receipts()
    limit = args.get("limit", 5)
    require_int(limit, "arguments.limit", 1)
    receipts: list[dict[str, Any]] = []
    for path in sorted(iter_receipt_paths(), reverse=True)[:limit]:
        receipt = load_receipt(path)
        receipts.append(
            {
                "receipt_id": receipt["receipt_id"],
                "recorded_on": receipt["recorded_on"],
                "applied_on": receipt["applied_on"],
                "workflow_id": receipt["workflow_id"],
                "source_commit": receipt["source_commit"],
                "summary": receipt["summary"],
            }
        )
    return {"count": len(receipts), "receipts": receipts}


def tool_get_workflow_contract(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    workflow_id = require_str(args.get("workflow_id"), "arguments.workflow_id")
    _secret_manifest, workflow_catalog, _command_catalog = load_catalog_context()
    workflow = workflow_catalog["workflows"].get(workflow_id)
    if workflow is None:
        raise ValueError(f"unknown workflow '{workflow_id}'")
    return workflow


def tool_get_command_contract(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    command_id = require_str(args.get("command_id"), "arguments.command_id")
    _secret_manifest, _workflow_catalog, command_catalog = load_catalog_context()
    command = command_catalog["commands"].get(command_id)
    if command is None:
        raise ValueError(f"unknown command '{command_id}'")
    return command


def tool_get_api_publication_surface(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    surface_id = require_str(args.get("surface_id"), "arguments.surface_id")
    _api_catalog, tiers, surfaces = load_api_publication_catalog()
    surface = next((item for item in surfaces if item["id"] == surface_id), None)
    if surface is None:
        raise ValueError(f"unknown API publication surface '{surface_id}'")
    return {
        **surface,
        "tier_summary": tiers[surface["publication_tier"]]["summary"],
    }


def tool_export_mcp_tools(registry: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    tools = render_mcp_tools(registry)
    output_path = args.get("output_path")
    if output_path is not None:
        output_file = Path(require_str(output_path, "arguments.output_path")).expanduser()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps({"tools": tools}, indent=2) + "\n")
    return {"count": len(tools), "tools": tools}


def tool_query_platform_context(tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    question = require_str(args.get("question"), "arguments.question")
    top_k = require_int(args.get("top_k", 5), "arguments.top_k", 1)
    token = read_secret_file(resolve_platform_context_token_path(), "platform-context API token")
    request = urllib.request.Request(
        require_str(tool.get("endpoint"), f"{tool['name']}.endpoint"),
        method="POST",
        data=json.dumps({"question": question, "top_k": top_k}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return require_mapping(
                json.loads(response.read().decode("utf-8")),
                "platform-context response",
            )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"platform-context API query failed with HTTP {exc.code}: {detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"platform-context API query failed: {exc.reason}") from exc


def normalize_approval_args(args: dict[str, Any]) -> dict[str, Any]:
    requester_class = require_str(args.get("requester_class"), "arguments.requester_class")
    if requester_class not in ALLOWED_IDENTITY_CLASSES:
        raise ValueError(f"arguments.requester_class must be one of {sorted(ALLOWED_IDENTITY_CLASSES)}")
    approver_classes = args.get("approver_classes", [])
    approver_classes = require_list(approver_classes, "arguments.approver_classes")
    normalized_approvers = [
        require_str(item, f"arguments.approver_classes[{index}]")
        for index, item in enumerate(approver_classes)
    ]
    return {
        "requester_class": requester_class,
        "approver_classes": normalized_approvers,
        "preflight_passed": bool(args.get("preflight_passed", False)),
        "validation_passed": bool(args.get("validation_passed", False)),
        "receipt_planned": bool(args.get("receipt_planned", False)),
        "self_approve": bool(args.get("self_approve", False)),
        "break_glass": bool(args.get("break_glass", False)),
    }


def tool_check_command_approval(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    command_id = require_str(args.get("command_id"), "arguments.command_id")
    secret_manifest, workflow_catalog, command_catalog = load_catalog_context()
    validate_secret_manifest(secret_manifest)
    verdict = evaluate_approval(
        command_catalog,
        workflow_catalog,
        command_id,
        **normalize_approval_args(args),
    )
    return {
        "approved": verdict["approved"],
        "command_id": command_id,
        "workflow_id": verdict["workflow_id"],
        "entrypoint": verdict["entrypoint"],
        "reasons": verdict["reasons"],
    }


def tool_run_governed_command(_tool: dict[str, Any], args: dict[str, Any]) -> tuple[dict[str, Any], str]:
    command_id = require_str(args.get("command_id"), "arguments.command_id")
    dry_run = bool(args.get("dry_run", True))
    secret_manifest, workflow_catalog, command_catalog = load_catalog_context()
    validate_secret_manifest(secret_manifest)
    verdict = evaluate_approval(
        command_catalog,
        workflow_catalog,
        command_id,
        **normalize_approval_args(args),
    )
    if not verdict["approved"]:
        return (
            {
                "approved": False,
                "executed": False,
                "command_id": command_id,
                "workflow_id": verdict["workflow_id"],
                "entrypoint": verdict["entrypoint"],
                "reasons": verdict["reasons"],
            },
            "rejected",
        )

    if dry_run:
        return (
            {
                "approved": True,
                "executed": False,
                "command_id": command_id,
                "workflow_id": verdict["workflow_id"],
                "entrypoint": verdict["entrypoint"],
                "reasons": [],
            },
            "success",
        )

    command = shlex.split(verdict["entrypoint"])
    process = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    result = {
        "approved": True,
        "executed": process.returncode == 0,
        "command_id": command_id,
        "workflow_id": verdict["workflow_id"],
        "entrypoint": verdict["entrypoint"],
        "reasons": [] if process.returncode == 0 else [process.stderr.strip() or "command execution failed"],
        "returncode": process.returncode,
    }
    outcome = "success" if process.returncode == 0 else "failure"
    return result, outcome


HANDLERS: Final[dict[str, Any]] = {
    "get_platform_status": tool_get_platform_status,
    "list_recent_receipts": tool_list_recent_receipts,
    "get_workflow_contract": tool_get_workflow_contract,
    "get_command_contract": tool_get_command_contract,
    "get_api_publication_surface": tool_get_api_publication_surface,
    "export_mcp_tools": tool_export_mcp_tools,
    "query_platform_context": tool_query_platform_context,
    "check_command_approval": tool_check_command_approval,
    "run_governed_command": tool_run_governed_command,
}


def make_tool_result(
    tool: dict[str, Any],
    structured_content: dict[str, Any],
    *,
    is_error: bool = False,
) -> dict[str, Any]:
    validate_instance(structured_content, tool["output_schema"], f"tool-result.{tool['name']}")
    return {
        "tool": tool["name"],
        "structuredContent": structured_content,
        "content": [
            {
                "type": "text",
                "text": json.dumps(structured_content, sort_keys=True),
            }
        ],
        "isError": is_error,
    }


def call_tool(
    registry: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
    *,
    actor_class: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    tool_index = build_tool_index(registry)
    tool = tool_index.get(tool_name)
    if tool is None:
        raise ValueError(f"unknown tool '{tool_name}'")
    validate_instance(arguments, tool["input_schema"], f"arguments.{tool_name}")

    handler_name = tool["implementation"]["handler"]
    handler = HANDLERS.get(handler_name)
    if handler is None:
        raise ValueError(f"tool '{tool_name}' references unsupported handler '{handler_name}'")

    correlation_id = str(uuid.uuid4())
    outcome = "success"
    summary = ""
    result: dict[str, Any]
    try:
        if handler_name == "run_governed_command":
            structured_content, outcome = handler(tool, arguments)
            is_error = outcome != "success"
        elif handler_name == "export_mcp_tools":
            structured_content = handler(registry, arguments)
            is_error = False
        else:
            structured_content = handler(tool, arguments)
            is_error = False
        result = make_tool_result(tool, structured_content, is_error=is_error)
        summary = f"{tool_name} completed with outcome {outcome}"
    except Exception as exc:
        outcome = "failure"
        summary = f"{tool_name} failed: {exc}"
        result = {
            "tool": tool_name,
            "structuredContent": {"error": str(exc)},
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        }

    audit_event = {
        "ts": utc_now_iso(),
        "tool": tool_name,
        "category": tool["category"],
        "transport": tool["transport"],
        "actor_class": actor_class,
        "outcome": outcome,
        "correlation_id": correlation_id,
        "arguments": arguments,
        "summary": summary,
        "details": {
            "endpoint": tool["endpoint"],
            "approval_required": tool["approval_required"],
        },
    }
    emit_tool_call_audit_event(registry, audit_event)
    return result, audit_event


def list_tools(registry: dict[str, Any]) -> int:
    print(f"Agent tool registry: {AGENT_TOOL_REGISTRY_PATH}")
    print("Available tools:")
    for tool in registry["tools"]:
        print(
            f"  - {tool['name']} [{tool['category']}, {tool['transport']}]: {tool['title']}"
        )
    return 0


def show_tool(registry: dict[str, Any], tool_name: str) -> int:
    tool_index = build_tool_index(registry)
    tool = tool_index.get(tool_name)
    if tool is None:
        print(f"Unknown tool: {tool_name}", file=sys.stderr)
        return 2
    print(f"Tool: {tool['name']}")
    print(f"Title: {tool['title']}")
    print(f"Description: {tool['description']}")
    print(f"Category: {tool['category']}")
    print(f"Transport: {tool['transport']}")
    print(f"Endpoint: {tool['endpoint']}")
    print(f"Auth: {tool['auth']}")
    print(f"Approval required: {tool['approval_required']}")
    print(f"Audit on call: {tool['audit_on_call']}")
    print(f"Runbook: {tool['runbook']}")
    if tool.get("catalog_refs"):
        print("Catalog refs:")
        for key, value in tool["catalog_refs"].items():
            print(f"  - {key}: {value}")
    print("Input schema:")
    print(json.dumps(tool["input_schema"], indent=2))
    print("Output schema:")
    print(json.dumps(tool["output_schema"], indent=2))
    return 0


def export_mcp(registry: dict[str, Any], output_path: str | None) -> int:
    payload = {"tools": render_mcp_tools(registry)}
    rendered = json.dumps(payload, indent=2) + "\n"
    if output_path:
        output_file = Path(output_path).expanduser()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(rendered)
        print(output_file)
        return 0
    sys.stdout.write(rendered)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect, validate, export, or call the governed LV3 agent tool registry."
    )
    parser.add_argument("--list", action="store_true", help="List available governed tools.")
    parser.add_argument("--tool", help="Show one governed tool.")
    parser.add_argument("--validate", action="store_true", help="Validate the governed tool registry.")
    parser.add_argument("--export-mcp", action="store_true", help="Export MCP-compatible tool definitions.")
    parser.add_argument("--output", help="Optional path for --export-mcp output.")
    parser.add_argument("--call", help="Call one governed tool.")
    parser.add_argument("--args-json", default="{}", help="JSON object of arguments for --call.")
    parser.add_argument(
        "--actor-class",
        default="agent",
        help="Identity class for audit records when using --call.",
    )
    args = parser.parse_args()

    try:
        registry, _workflow_catalog = load_agent_tool_registry()
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        return emit_cli_error("Agent tool registry", exc)

    if args.validate:
        print(f"Agent tool registry OK: {AGENT_TOOL_REGISTRY_PATH}")
        return 0
    if args.export_mcp:
        return export_mcp(registry, args.output)
    if args.call:
        try:
            arguments = require_mapping(json.loads(args.args_json), "args-json")
        except json.JSONDecodeError as exc:
            return emit_cli_error("Agent tool registry", exc)
        try:
            result, audit_event = call_tool(
                registry,
                args.call,
                arguments,
                actor_class=require_str(args.actor_class, "--actor-class"),
            )
        except (ValueError, RuntimeError) as exc:
            return emit_cli_error("Agent tool registry", exc)
        print(json.dumps({"result": result, "audit_event": audit_event}, indent=2))
        return 0 if not result.get("isError") else 1
    if args.tool:
        return show_tool(registry, args.tool)
    return list_tools(registry)


if __name__ == "__main__":
    sys.exit(main())
