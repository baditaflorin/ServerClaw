#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import os
import sys
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_bool, require_int, require_list, require_mapping, require_str

from api_publication import load_api_publication_catalog
from command_catalog import (
    ALLOWED_IDENTITY_CLASSES,
    evaluate_approval,
    load_command_catalog,
    validate_command_catalog,
)
from controller_automation_toolkit import REPO_ROOT, emit_cli_error, load_json, load_yaml, repo_path
from deployment_history import query_deployment_history
from governed_command import execute_governed_command
from live_apply_receipts import iter_receipt_paths, load_receipt, validate_receipts
from maintenance_window_tool import list_active_windows_best_effort
from platform.use_cases.serverclaw_skills import list_serverclaw_skill_packs
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
SERVICE_CATALOG_PATH: Final[Path] = repo_path("config", "service-capability-catalog.json")
AUDIT_LOG_ENV: Final[str] = "LV3_AGENT_TOOL_AUDIT_LOG_PATH"
PLATFORM_CONTEXT_TOKEN_ENV: Final[str] = "LV3_PLATFORM_CONTEXT_API_TOKEN_FILE"
PLATFORM_CONTEXT_TOKEN_VALUE_ENV: Final[str] = "LV3_GATEWAY_PLATFORM_CONTEXT_LEGACY_TOKEN"
PLATFORM_CONTEXT_API_URL_ENV: Final[str] = "LV3_PLATFORM_CONTEXT_API_URL"
BROWSER_RUNNER_BASE_URL_ENV: Final[str] = "LV3_BROWSER_RUNNER_BASE_URL"
DEFAULT_PLATFORM_CONTEXT_TOKEN_PATH: Final[Path] = REPO_ROOT / ".local" / "platform-context" / "api-token.txt"
PORTAINER_BASE_URL_ENV: Final[str] = "LV3_PORTAINER_BASE_URL"
PORTAINER_USERNAME_ENV: Final[str] = "LV3_PORTAINER_USERNAME"
PORTAINER_PASSWORD_ENV: Final[str] = "LV3_PORTAINER_PASSWORD"
PORTAINER_ENDPOINT_ID_ENV: Final[str] = "LV3_PORTAINER_ENDPOINT_ID"
PORTAINER_VERIFY_SSL_ENV: Final[str] = "LV3_PORTAINER_VERIFY_SSL"
DEFAULT_PORTAINER_AUTH_FILE_PATH: Final[Path] = REPO_ROOT / ".local" / "portainer" / "admin-auth.json"
SUPPORTED_SCHEMA_VERSION: Final[str] = "1.0.0"
ALLOWED_TOOL_CATEGORIES: Final[set[str]] = {"observe", "report", "execute", "approve"}
ALLOWED_TRANSPORTS: Final[set[str]] = {"controller_local", "http", "nats", "ansible"}


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
        value = require_int(instance, path, minimum=schema.get("minimum"))
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


def resolve_platform_context_token() -> str:
    """Resolve the platform-context API token.

    Checks (in order):
    1. Direct token value from LV3_GATEWAY_PLATFORM_CONTEXT_LEGACY_TOKEN env var
       (set by the api-gateway.env.j2 template — avoids needing a file mount)
    2. Token file path from LV3_PLATFORM_CONTEXT_API_TOKEN_FILE env var
    3. Default file path at REPO_ROOT/.local/platform-context/api-token.txt
    """
    direct = os.environ.get(PLATFORM_CONTEXT_TOKEN_VALUE_ENV, "").strip()
    if direct:
        return direct
    return read_secret_file(resolve_platform_context_token_path(), "platform-context API token")


def resolve_portainer_auth() -> dict[str, Any]:
    base_url = os.environ.get(PORTAINER_BASE_URL_ENV, "").strip()
    if base_url:
        return {
            "base_url": base_url,
            "username": os.environ.get(PORTAINER_USERNAME_ENV, "ops-portainer"),
            "password": os.environ.get(PORTAINER_PASSWORD_ENV, ""),
            "endpoint_id": os.environ.get(PORTAINER_ENDPOINT_ID_ENV, "1"),
            "verify_ssl": os.environ.get(PORTAINER_VERIFY_SSL_ENV, "false").lower() == "true",
        }
    return load_json(DEFAULT_PORTAINER_AUTH_FILE_PATH)


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


def load_service_catalog() -> list[dict[str, Any]]:
    payload = require_mapping(load_json(SERVICE_CATALOG_PATH), str(SERVICE_CATALOG_PATH))
    return require_list(payload.get("services"), "config/service-capability-catalog.json.services")


def resolve_service_base_url(service_id: str, *, env_var: str | None = None) -> str:
    if env_var:
        override = os.environ.get(env_var)
        if override:
            return require_str(override, f"environment.{env_var}").rstrip("/")

    for index, service in enumerate(load_service_catalog()):
        service = require_mapping(service, f"config/service-capability-catalog.json.services[{index}]")
        current_id = require_str(service.get("id"), f"config/service-capability-catalog.json.services[{index}].id")
        if current_id != service_id:
            continue

        for field in ("internal_url", "public_url"):
            value = service.get(field)
            if value is not None:
                return require_str(
                    value,
                    f"config/service-capability-catalog.json.services[{index}].{field}",
                ).rstrip("/")

        environments = require_mapping(
            service.get("environments", {}),
            f"config/service-capability-catalog.json.services[{index}].environments",
        )
        production = environments.get("production")
        if production is not None:
            production = require_mapping(
                production,
                f"config/service-capability-catalog.json.services[{index}].environments.production",
            )
            if production.get("url") is not None:
                return require_str(
                    production.get("url"),
                    f"config/service-capability-catalog.json.services[{index}].environments.production.url",
                ).rstrip("/")

        raise ValueError(f"service '{service_id}' does not define an internal or production URL")

    raise ValueError(f"service '{service_id}' is not present in config/service-capability-catalog.json")


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
    require_int(limit, "arguments.limit", minimum=1)
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


def tool_get_deployment_history(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    service_id = args.get("service_id")
    if service_id is not None:
        service_id = require_str(service_id, "arguments.service_id")
    environment = args.get("environment")
    if environment is not None:
        environment = require_str(environment, "arguments.environment")
    days = require_int(args.get("days", 30), "arguments.days", minimum=1)
    return query_deployment_history(service_id=service_id, environment=environment, days=days)


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
    top_k = require_int(args.get("top_k", 5), "arguments.top_k", minimum=1)
    token = resolve_platform_context_token()
    endpoint_override = os.environ.get(PLATFORM_CONTEXT_API_URL_ENV, "").strip()
    endpoint = endpoint_override if endpoint_override else require_str(
        tool.get("endpoint"), f"{tool['name']}.endpoint"
    )
    request = urllib.request.Request(
        endpoint,
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


def tool_browser_run_session(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from browser_runner_client import DEFAULT_TIMEOUT_SECONDS, run_session

    base_url = resolve_service_base_url("browser_runner", env_var=BROWSER_RUNNER_BASE_URL_ENV)
    timeout_seconds = require_int(
        args.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        "arguments.timeout_seconds",
        minimum=1,
    )
    payload = dict(args)
    return run_session(base_url, payload, timeout_seconds=timeout_seconds)


def tool_get_maintenance_windows(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    service_id = args.get("service_id")
    if service_id is not None:
        service_id = require_str(service_id, "arguments.service_id")
    windows = list_active_windows_best_effort()
    payload = [windows[key] for key in sorted(windows)]
    if service_id:
        payload = [window for window in payload if window["service_id"] in {service_id, "all"}]
    return {
        "count": len(payload),
        "windows": payload,
    }


def tool_list_serverclaw_skills(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    workspace_id = args.get("workspace_id")
    if workspace_id is not None:
        workspace_id = require_str(workspace_id, "arguments.workspace_id")
    skill_id = args.get("skill_id")
    if skill_id is not None:
        skill_id = require_str(skill_id, "arguments.skill_id")
    return list_serverclaw_skill_packs(
        workspace_id=workspace_id,
        skill_id=skill_id,
        include_imported=bool(args.get("include_imported", True)),
        include_prompt_manifest=bool(args.get("include_prompt_manifest", False)),
    )


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
    return execute_governed_command(
        command_id=require_str(args.get("command_id"), "arguments.command_id"),
        requester_class=require_str(args.get("requester_class"), "arguments.requester_class"),
        approver_classes=require_list(args.get("approver_classes", []), "arguments.approver_classes"),
        preflight_passed=bool(args.get("preflight_passed", False)),
        validation_passed=bool(args.get("validation_passed", False)),
        receipt_planned=bool(args.get("receipt_planned", False)),
        self_approve=bool(args.get("self_approve", False)),
        break_glass=bool(args.get("break_glass", False)),
        parameters=require_mapping(args.get("parameters", {}), "arguments.parameters"),
        dry_run=bool(args.get("dry_run", True)),
    )


DOCKER_SOCKET_PATH: Final[str] = "/var/run/docker.sock"


def _docker_socket_available() -> bool:
    return Path(DOCKER_SOCKET_PATH).exists()


def _docker_unix_connection(timeout: float = 30):  # type: ignore[return]
    """Create an HTTP connection over the Docker Unix socket."""
    import http.client
    import socket as _socket

    class _Conn(http.client.HTTPConnection):
        def __init__(self, socket_path: str, _timeout: float = 30):
            super().__init__("localhost", timeout=int(_timeout))
            self._socket_path = socket_path

        def connect(self) -> None:
            self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            self.sock.connect(self._socket_path)

    return _Conn(DOCKER_SOCKET_PATH, timeout)


def _docker_socket_request(method: str, path: str, params: dict[str, str] | None = None) -> Any:
    """Make a request to the Docker Engine API via the Unix socket."""
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_path = f"{path}?{query}"
    else:
        full_path = path

    conn = _docker_unix_connection()
    conn.request(method, full_path, headers={"Host": "localhost"})
    response = conn.getresponse()
    if response.status != 200:
        raise ValueError(f"Docker API returned HTTP {response.status}: {response.read().decode()}")
    return json.loads(response.read().decode("utf-8"))


def _docker_socket_json(method: str, path: str, body: dict[str, Any] | None = None,
                        *, accept_status: tuple[int, ...] = (200, 201, 204)) -> Any:
    """Docker Engine API request with optional JSON body.  Returns parsed JSON or None for 204."""
    conn = _docker_unix_connection(timeout=60)
    headers: dict[str, str] = {"Host": "localhost"}
    encoded_body: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        encoded_body = json.dumps(body).encode("utf-8")
    conn.request(method, path, body=encoded_body, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    if response.status not in accept_status:
        raise ValueError(f"Docker API {method} {path} returned HTTP {response.status}: {raw.decode()}")
    if response.status == 204 or not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def _docker_socket_raw(method: str, path: str, *, timeout: float = 30) -> bytes:
    """Docker Engine API request returning raw bytes (for log streams)."""
    conn = _docker_unix_connection(timeout=timeout)
    conn.request(method, path, headers={"Host": "localhost"})
    response = conn.getresponse()
    if response.status != 200:
        raise ValueError(f"Docker API {method} {path} returned HTTP {response.status}")
    return response.read()


def _portainer_available() -> bool:
    """Check whether Portainer credentials are configured."""
    base_url = os.environ.get(PORTAINER_BASE_URL_ENV, "").strip()
    if base_url:
        return True
    return DEFAULT_PORTAINER_AUTH_FILE_PATH.is_file()


def tool_list_containers(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    include_stopped = bool(args.get("include_stopped", False))

    if _portainer_available():
        from portainer_tool import PortainerClient  # lazy import
        client = PortainerClient(resolve_portainer_auth())
        client.login()
        containers = client.list_containers(all_containers=include_stopped)
        source = "portainer"
    elif _docker_socket_available():
        params = {"all": "1" if include_stopped else "0"}
        containers = _docker_socket_request("GET", "/containers/json", params)
        source = "docker-socket"
    else:
        raise ValueError(
            "Cannot list containers: no Portainer credentials configured and "
            "Docker socket not available at /var/run/docker.sock. "
            "Mount the Docker socket or provision Portainer credentials."
        )

    normalized = [
        {
            "id": c["Id"][:12],
            "names": [n.lstrip("/") for n in c.get("Names", [])],
            "image": c.get("Image", ""),
            "state": c.get("State", ""),
            "status": c.get("Status", ""),
        }
        for c in containers
    ]
    return {"count": len(normalized), "containers": normalized, "source": source}


def tool_get_container_logs(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    container = require_str(args.get("container"), "arguments.container")
    tail = require_int(args.get("tail", 100), "arguments.tail", minimum=1)

    if _portainer_available():
        from portainer_tool import PortainerClient  # lazy import
        client = PortainerClient(resolve_portainer_auth())
        client.login()
        logs = client.container_logs(container, tail)
    elif _docker_socket_available():
        # Resolve container name to ID via Docker API
        all_containers = _docker_socket_request("GET", "/containers/json", {"all": "1"})
        target_id = None
        for c in all_containers:
            names = [n.lstrip("/") for n in c.get("Names", [])]
            if container in names or c["Id"].startswith(container):
                target_id = c["Id"]
                break
        if target_id is None:
            raise ValueError(f"Container not found: {container}")
        # Fetch logs — Docker API returns plain text for logs endpoint
        import http.client
        import socket

        class DockerUnixConnection(http.client.HTTPConnection):
            def __init__(self, socket_path: str, timeout: float = 30):
                super().__init__("localhost", timeout=int(timeout))
                self._socket_path = socket_path

            def connect(self) -> None:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(self.timeout)
                self.sock.connect(self._socket_path)

        conn = DockerUnixConnection(DOCKER_SOCKET_PATH)
        conn.request(
            "GET",
            f"/containers/{target_id}/logs?stdout=1&stderr=1&tail={tail}",
            headers={"Host": "localhost"},
        )
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError(f"Docker API returned HTTP {response.status}")
        from portainer_tool import decode_docker_log_stream
        logs = decode_docker_log_stream(response.read())
    else:
        raise ValueError(
            "Cannot get container logs: no Portainer credentials configured and "
            "Docker socket not available."
        )

    return {"container": container, "tail": tail, "logs": logs}


DEFAULT_NOMAD_API_URL: Final[str] = "https://100.64.0.1:8013"
DEFAULT_NOMAD_TOKEN_PATH: Final[Path] = REPO_ROOT / ".local" / "nomad" / "tokens" / "bootstrap-management.token"
DEFAULT_NOMAD_CA_CERT_PATH: Final[Path] = REPO_ROOT / ".local" / "nomad" / "tls" / "nomad-agent-ca.pem"


def _nomad_request(method: str, path: str, *, params: dict | None = None, json_body: dict | None = None) -> dict[str, Any]:
    import requests  # lazy import

    token_file = DEFAULT_NOMAD_TOKEN_PATH
    if not token_file.is_file():
        raise RuntimeError(f"Nomad management token not found at {token_file}")
    token = token_file.read_text().strip()
    ca_cert = str(DEFAULT_NOMAD_CA_CERT_PATH) if DEFAULT_NOMAD_CA_CERT_PATH.is_file() else False
    url = f"{DEFAULT_NOMAD_API_URL}{path}"
    resp = requests.request(
        method, url,
        headers={"X-Nomad-Token": token},
        params=params,
        json=json_body,
        verify=ca_cert,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def tool_list_nomad_jobs(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    namespace = args.get("namespace", "*")
    jobs_raw = _nomad_request("GET", "/v1/jobs", params={"namespace": namespace})
    jobs = [
        {
            "id": j.get("ID", ""),
            "name": j.get("Name", ""),
            "type": j.get("Type", ""),
            "status": j.get("Status", ""),
            "namespace": j.get("Namespace", "default"),
        }
        for j in jobs_raw
    ]
    return {"count": len(jobs), "jobs": jobs}


def tool_get_nomad_job_status(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    job_id = require_str(args.get("job_id"), "arguments.job_id")
    namespace = args.get("namespace", "default")
    job = _nomad_request("GET", f"/v1/job/{job_id}", params={"namespace": namespace})
    return {
        "id": job.get("ID", ""),
        "name": job.get("Name", ""),
        "type": job.get("Type", ""),
        "status": job.get("Status", ""),
        "namespace": job.get("Namespace", "default"),
    }


def tool_dispatch_nomad_job(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    job_id = require_str(args.get("job_id"), "arguments.job_id")
    meta = args.get("meta", {})
    namespace = args.get("namespace", "default")
    result = _nomad_request(
        "POST", f"/v1/job/{job_id}/dispatch",
        params={"namespace": namespace},
        json_body={"Meta": meta},
    )
    return {
        "dispatch_id": result.get("DispatchedJobID", ""),
        "eval_id": result.get("EvalID", ""),
    }


# ---------------------------------------------------------------------------
# Generic service auth helper (ADR 0362)
# ---------------------------------------------------------------------------


def _resolve_service_auth(service_name: str) -> dict[str, Any]:
    """Discover credentials for a named service following the ADR 0362 convention.

    Precedence:
      1. LV3_{SERVICE}_AUTH_FILE env var (absolute path to auth JSON)
      2. .local/{service}/admin-auth.json  (structured: base_url + api_token + extras)
      3. .local/{service}/api-token.txt    (single token; base_url from JSON if present)
    """
    env_var = f"LV3_{service_name.upper()}_AUTH_FILE"
    env_override = os.environ.get(env_var)
    if env_override:
        auth_path = Path(env_override)
        if not auth_path.is_file():
            raise RuntimeError(f"{env_var} points to missing file: {auth_path}")
        return json.loads(auth_path.read_text())

    admin_auth = REPO_ROOT / ".local" / service_name / "admin-auth.json"
    if admin_auth.is_file():
        return json.loads(admin_auth.read_text())

    token_file = REPO_ROOT / ".local" / service_name / "api-token.txt"
    if token_file.is_file():
        return {"api_token": token_file.read_text().strip()}

    raise RuntimeError(
        f"No credentials found for service '{service_name}'. "
        f"Expected {admin_auth} or {token_file}, or set {env_var}."
    )


# ---------------------------------------------------------------------------
# Plane tools (ADR 0362 gateway pattern, ADR 0363)
# ---------------------------------------------------------------------------


def _resolve_plane_auth() -> dict[str, Any]:
    return _resolve_service_auth("plane")


def _plane_client():  # type: ignore[return]
    from platform.ansible.plane import PlaneClient  # lazy import

    auth = _resolve_plane_auth()
    return PlaneClient(
        base_url=auth["base_url"],
        api_token=auth["api_token"],
        verify_ssl=auth.get("verify_ssl", True),
    ), auth


def _resolve_plane_project(client, workspace_slug: str, identifier: str) -> str:
    projects = client.list_projects(workspace_slug)
    for p in projects:
        if p.get("identifier") == identifier:
            return p["id"]
    raise RuntimeError(f"Plane project with identifier '{identifier}' not found")


def _resolve_state_id(client, workspace_slug: str, project_id: str, state_name: str) -> str:
    states = client.list_states(workspace_slug, project_id)
    for s in states:
        if s.get("name", "").lower() == state_name.lower():
            return s["id"]
    available = ", ".join(s.get("name", "") for s in states)
    raise RuntimeError(f"Plane state '{state_name}' not found; available: {available}")


def tool_list_plane_tasks(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    client, auth = _plane_client()
    ws = auth["workspace_slug"]
    identifier = args.get("project", "AW")
    project_id = _resolve_plane_project(client, ws, identifier)
    issues = client.list_issues(ws, project_id)
    state_filter = args.get("state_name")
    if state_filter:
        states = client.list_states(ws, project_id)
        state_map = {s["id"]: s.get("name", "") for s in states}
        issues = [i for i in issues if state_map.get(i.get("state"), "").lower() == state_filter.lower()]
    else:
        states = client.list_states(ws, project_id)
        state_map = {s["id"]: s.get("name", "") for s in states}
    tasks = [
        {
            "id": i.get("id", ""),
            "name": i.get("name", ""),
            "state_name": state_map.get(i.get("state"), ""),
            "priority": i.get("priority"),
            "created_at": i.get("created_at", ""),
        }
        for i in issues
    ]
    return {"count": len(tasks), "project": identifier, "tasks": tasks}


def tool_get_plane_task(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    client, auth = _plane_client()
    ws = auth["workspace_slug"]
    issue_id = require_str(args.get("issue_id"), "arguments.issue_id")
    identifier = args.get("project", "AW")
    project_id = _resolve_plane_project(client, ws, identifier)
    _status, issue = client._request(
        f"/api/v1/workspaces/{ws}/projects/{project_id}/issues/{issue_id}/",
    )
    states = client.list_states(ws, project_id)
    state_map = {s["id"]: s.get("name", "") for s in states}
    issue["state_name"] = state_map.get(issue.get("state"), "")
    return issue


def tool_create_plane_task(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    client, auth = _plane_client()
    ws = auth["workspace_slug"]
    title = require_str(args.get("title"), "arguments.title")
    identifier = args.get("project", "AW")
    project_id = _resolve_plane_project(client, ws, identifier)
    payload: dict[str, Any] = {"name": title}
    if "description_html" in args:
        payload["description_html"] = args["description_html"]
    if "priority" in args:
        payload["priority"] = args["priority"]
    state_name = args.get("state_name", "Todo")
    payload["state"] = _resolve_state_id(client, ws, project_id, state_name)
    if "label_names" in args:
        existing_labels = client.list_labels(ws, project_id)
        label_map = {lb.get("name", "").lower(): lb["id"] for lb in existing_labels}
        label_ids = []
        for name in args["label_names"]:
            lid = label_map.get(name.lower())
            if not lid:
                new_label = client.create_label(ws, project_id, name)
                lid = new_label["id"]
            label_ids.append(lid)
        payload["labels"] = label_ids
    issue = client.create_issue(ws, project_id, payload)
    return {
        "id": issue.get("id", ""),
        "name": issue.get("name", ""),
        "state_name": state_name,
        "project_identifier": identifier,
    }


def tool_update_plane_task(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    client, auth = _plane_client()
    ws = auth["workspace_slug"]
    issue_id = require_str(args.get("issue_id"), "arguments.issue_id")
    identifier = args.get("project", "AW")
    project_id = _resolve_plane_project(client, ws, identifier)
    payload: dict[str, Any] = {}
    if "name" in args:
        payload["name"] = args["name"]
    if "description_html" in args:
        payload["description_html"] = args["description_html"]
    if "priority" in args:
        payload["priority"] = args["priority"]
    if "state_name" in args:
        payload["state"] = _resolve_state_id(client, ws, project_id, args["state_name"])
    if not payload:
        raise ValueError("At least one field to update must be provided")
    issue = client.update_issue(ws, project_id, issue_id, payload)
    return {
        "id": issue.get("id", ""),
        "name": issue.get("name", ""),
    }


def tool_add_plane_comment(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    client, auth = _plane_client()
    ws = auth["workspace_slug"]
    issue_id = require_str(args.get("issue_id"), "arguments.issue_id")
    comment_html = require_str(args.get("comment_html"), "arguments.comment_html")
    identifier = args.get("project", "AW")
    project_id = _resolve_plane_project(client, ws, identifier)
    comment = client.add_comment(ws, project_id, issue_id, comment_html)
    return {"id": comment.get("id", "")}


# ---------------------------------------------------------------------------
# Outline tools (ADR 0362 gateway pattern, ADR 0364)
# ---------------------------------------------------------------------------


def _outline_client():  # type: ignore[return]
    from outline_client import OutlineClient  # lazy import

    auth = _resolve_service_auth("outline")
    base_url = auth.get("base_url", "https://wiki.localhost")
    api_token = auth.get("api_token") or auth.get("token")
    if not api_token:
        raise RuntimeError("Outline auth missing 'api_token' field")
    return OutlineClient(base_url=base_url, api_token=api_token)


def tool_list_outline_collections(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    client = _outline_client()
    response = client.call("collections.list", {})
    collections = [
        {
            "id": c.get("id", ""),
            "name": c.get("name", ""),
            "description": c.get("description", ""),
            "documents_count": c.get("documentsCount", 0),
        }
        for c in response.get("data", [])
    ]
    return {"count": len(collections), "collections": collections}


def tool_search_outline_documents(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    query = require_str(args.get("query"), "arguments.query")
    client = _outline_client()
    payload: dict[str, Any] = {"query": query, "limit": args.get("limit", 25)}
    if "collection_id" in args:
        payload["collectionId"] = args["collection_id"]
    response = client.call("documents.search", payload)
    results = [
        {
            "id": r.get("document", {}).get("id", ""),
            "title": r.get("document", {}).get("title", ""),
            "collection_id": r.get("document", {}).get("collectionId", ""),
            "url": r.get("document", {}).get("url", ""),
            "ranking": r.get("ranking"),
        }
        for r in response.get("data", [])
    ]
    return {"count": len(results), "query": query, "results": results}


def tool_get_outline_document(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    doc_id = require_str(args.get("document_id"), "arguments.document_id")
    client = _outline_client()
    response = client.call("documents.info", {"id": doc_id})
    doc = response.get("data", {})
    return {
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "text": doc.get("text", ""),
        "collection_id": doc.get("collectionId", ""),
        "url": doc.get("url", ""),
        "created_at": doc.get("createdAt", ""),
        "updated_at": doc.get("updatedAt", ""),
    }


def tool_create_outline_document(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    title = require_str(args.get("title"), "arguments.title")
    collection_id = require_str(args.get("collection_id"), "arguments.collection_id")
    client = _outline_client()
    payload: dict[str, Any] = {
        "title": title,
        "collectionId": collection_id,
        "text": args.get("text", ""),
        "publish": args.get("publish", True),
    }
    if "parent_document_id" in args:
        payload["parentDocumentId"] = args["parent_document_id"]
    response = client.call("documents.create", payload)
    doc = response.get("data", {})
    return {
        "id": doc.get("id", ""),
        "title": doc.get("title", ""),
        "url": doc.get("url", ""),
        "collection_id": doc.get("collectionId", ""),
    }


def tool_list_outline_documents(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    collection_id = require_str(args.get("collection_id"), "arguments.collection_id")
    client = _outline_client()
    # Paginate through all documents in the collection
    offset = 0
    limit = 100
    all_docs: list[dict[str, Any]] = []
    while True:
        response = client.call("documents.list", {
            "collectionId": collection_id,
            "limit": limit,
            "offset": offset,
        })
        batch = response.get("data", [])
        all_docs.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return {
        "collection_id": collection_id,
        "count": len(all_docs),
        "documents": [
            {
                k: v for k, v in {
                    "id": d.get("id", ""),
                    "title": d.get("title", ""),
                    "url": d.get("url", ""),
                    "parent_document_id": d.get("parentDocumentId"),
                    "updated_at": d.get("updatedAt", ""),
                }.items() if v is not None
            }
            for d in all_docs
        ],
    }


def tool_update_outline_document(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    document_id = require_str(args.get("document_id"), "arguments.document_id")
    client = _outline_client()
    payload: dict[str, Any] = {"id": document_id, "publish": True, "done": True}
    if "title" in args:
        payload["title"] = args["title"]
    if "text" in args:
        payload["text"] = args["text"]
    if not any(k in payload for k in ("title", "text")):
        raise ValueError("update-outline-document: at least one of 'title' or 'text' is required")
    response = client.call("documents.update", payload)
    doc = response.get("data", {})
    return {
        "id": doc.get("id", document_id),
        "title": doc.get("title", ""),
        "url": doc.get("url", ""),
        "collection_id": doc.get("collectionId", ""),
        "updated_at": doc.get("updatedAt", ""),
    }


def tool_upsert_outline_document(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Create-or-update by title within a collection (idempotent).

    Mirrors outline_tool.py document.publish: if a document with this title
    already exists in the collection, update it; otherwise create it.
    """
    title = require_str(args.get("title"), "arguments.title")
    collection_id = require_str(args.get("collection_id"), "arguments.collection_id")
    text = args.get("text", "")
    client = _outline_client()

    # Find existing document by title
    offset = 0
    limit = 100
    existing_id: str | None = None
    while True:
        response = client.call("documents.list", {
            "collectionId": collection_id,
            "limit": limit,
            "offset": offset,
        })
        batch = response.get("data", [])
        for d in batch:
            if d.get("title") == title:
                existing_id = d["id"]
                break
        if existing_id or len(batch) < limit:
            break
        offset += limit

    if existing_id:
        response = client.call("documents.update", {
            "id": existing_id,
            "title": title,
            "text": text,
            "publish": True,
            "done": True,
        })
        doc = response.get("data", {})
        return {
            "id": doc.get("id", existing_id),
            "title": title,
            "url": doc.get("url", ""),
            "collection_id": collection_id,
            "outcome": "updated",
        }
    else:
        payload: dict[str, Any] = {
            "collectionId": collection_id,
            "title": title,
            "text": text,
            "publish": True,
        }
        if "parent_document_id" in args:
            payload["parentDocumentId"] = args["parent_document_id"]
        response = client.call("documents.create", payload)
        doc = response.get("data", {})
        return {
            "id": doc.get("id", ""),
            "title": title,
            "url": doc.get("url", ""),
            "collection_id": collection_id,
            "outcome": "created",
        }


def tool_delete_outline_document(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    document_id = require_str(args.get("document_id"), "arguments.document_id")
    client = _outline_client()
    client.call("documents.delete", {"id": document_id})
    return {"deleted": True, "document_id": document_id}


def tool_provision_outline_api_token(
    _tool: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    """Provision a new Outline API token via direct DB insertion.

    This is the self-service credential rotation path for agents. When Outline
    tools return 401, call this first, then retry the failed operation.
    """
    # Lazy import to avoid module-load side effects (subprocess calls, etc.)
    import importlib.util
    import sys as _sys

    script_path = REPO_ROOT / "scripts" / "provision_outline_api_token.py"
    spec = importlib.util.spec_from_file_location("provision_outline_api_token", script_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    name = args.get("name", "agent-automation")
    dry_run = bool(args.get("dry_run", False))

    token = mod.provision(name=name, dry_run=dry_run)

    auth_file = str(REPO_ROOT / ".local" / "outline" / "admin-auth.json")
    return {
        "token_preview": f"{token[:20]}...{token[-4:]}",
        "auth_file": auth_file,
    }


# MemPalace Memory Tools
def tool_mempalace_search(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Search MemPalace for memories matching a query."""
    import subprocess

    query = require_str(args.get("query"), "arguments.query")
    wing = args.get("wing", "proxmox_florin")
    limit = args.get("limit", 10)

    try:
        result = subprocess.run(
            ["python3", "-m", "mempalace", "search", query, "--limit", str(limit)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"MemPalace search failed: {result.stderr}",
                "query": query,
                "results": [],
            }

        # Parse search results from output
        import json as _json
        try:
            output_lines = result.stdout.strip().split("\n")
            results = []
            for line in output_lines:
                if line.startswith("{"):
                    results.append(_json.loads(line))
        except Exception:
            results = []

        return {
            "status": "success",
            "query": query,
            "wing": wing,
            "count": len(results),
            "results": results[:limit],
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "message": "MemPalace search timed out",
            "query": query,
            "results": [],
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "query": query,
            "results": [],
        }


def tool_mempalace_add_drawer(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Save a discovery or insight to MemPalace."""
    import subprocess

    content = require_str(args.get("content"), "arguments.content")
    wing = args.get("wing", "proxmox_florin")
    room = args.get("room", "discoveries")

    try:
        result = subprocess.run(
            ["python3", "-m", "mempalace", "add-drawer", content],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to save to MemPalace: {result.stderr}",
                "content": content[:100],
            }

        return {
            "status": "success",
            "message": "Memory saved to MemPalace",
            "wing": wing,
            "room": room,
            "content_preview": content[:150],
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "message": "MemPalace save operation timed out",
            "content": content[:100],
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "content": content[:100],
        }


def tool_mempalace_wake_up(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Load critical facts from MemPalace at session start."""
    import subprocess

    wing = args.get("wing", "proxmox_florin")

    try:
        result = subprocess.run(
            ["python3", "-m", "mempalace", "wake-up", "--wing", wing],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to load critical facts: {result.stderr}",
                "wing": wing,
                "facts": "",
            }

        return {
            "status": "success",
            "wing": wing,
            "facts": result.stdout.strip(),
            "message": "Critical facts loaded from MemPalace",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "message": "MemPalace wake-up timed out",
            "wing": wing,
            "facts": "",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "wing": wing,
            "facts": "",
        }


def tool_mempalace_status(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Get MemPalace palace status and memory counts."""
    import subprocess

    try:
        result = subprocess.run(
            ["python3", "-m", "mempalace", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to get MemPalace status: {result.stderr}",
            }

        # Parse status output to extract key metrics
        import re
        output = result.stdout
        drawers = 0
        rooms = {}

        for line in output.split("\n"):
            if "drawers" in line.lower():
                match = re.search(r"(\d+)\s+drawers", line)
                if match:
                    drawers = int(match.group(1))
            if "room:" in line.lower():
                match = re.search(r"room:\s+(\w+)\s+(\d+)", line)
                if match:
                    rooms[match.group(1)] = int(match.group(2))

        return {
            "status": "success",
            "total_drawers": drawers,
            "rooms": rooms,
            "message": f"MemPalace palace has {drawers} indexed memories",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "message": "MemPalace status check timed out",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }


# Host Command Execution
_HOST_COMMAND_BLOCKED_PATTERNS: Final[list[str]] = [
    "rm -rf /",
    "mkfs",
    "dd if=/dev/zero",
    "dd if=/dev/urandom",
    ":(){ :",
    "> /dev/sd",
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
    "passwd",
    "userdel",
]

_HOST_COMMAND_EXEC_IMAGE: Final[str] = "debian:bookworm-slim"


def _strip_docker_log_header(raw: bytes) -> str:
    """Strip Docker multiplexed stream headers from log output.

    Docker log API with stdout/stderr returns 8-byte framed messages:
      [stream_type(1) + 0(3) + size(4 big-endian)] + payload
    """
    lines: list[str] = []
    offset = 0
    while offset + 8 <= len(raw):
        size = int.from_bytes(raw[offset + 4 : offset + 8], "big")
        if offset + 8 + size > len(raw):
            break
        lines.append(raw[offset + 8 : offset + 8 + size].decode("utf-8", errors="replace"))
        offset += 8 + size
    if not lines:
        return raw.decode("utf-8", errors="replace")
    return "".join(lines)


def tool_execute_host_command(_tool: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Execute a shell command on the Docker host via a temporary container.

    Uses the Docker Engine API to create a one-shot container with read-only
    access to the host root filesystem (mounted at /host).  The container is
    automatically removed after execution.
    """
    command = require_str(args.get("command"), "arguments.command")
    timeout_secs = require_int(args.get("timeout", 30), "arguments.timeout", minimum=1)

    # Safety filter — block obviously destructive patterns
    cmd_lower = command.lower()
    for pattern in _HOST_COMMAND_BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return {
                "status": "blocked",
                "command": command,
                "exit_code": -1,
                "stdout": "(blocked)",
                "stderr": f"Command blocked by safety filter: contains '{pattern}'",
                "host": "runtime-control-lv3",
            }

    if not _docker_socket_available():
        raise ValueError(
            "Cannot execute host commands: Docker socket not available at "
            f"{DOCKER_SOCKET_PATH}. Mount the Docker socket to enable this tool."
        )

    # Create a temporary container with host root mounted read-only
    create_resp = _docker_socket_json("POST", "/containers/create", body={
        "Image": _HOST_COMMAND_EXEC_IMAGE,
        "Cmd": ["bash", "-c", command],
        "HostConfig": {
            "AutoRemove": False,
            "NetworkMode": "host",
            "PidMode": "host",
            "ReadonlyRootfs": False,
            "Binds": ["/:/host:ro"],
        },
        "WorkingDir": "/host",
        "Env": [
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "TERM=xterm",
        ],
    })
    container_id = require_str(create_resp.get("Id"), "container creation response.Id")

    try:
        # Start the container
        _docker_socket_json("POST", f"/containers/{container_id}/start",
                            accept_status=(204, 304))

        # Wait for it to finish (with timeout)
        wait_resp = _docker_socket_json(
            "POST",
            f"/containers/{container_id}/wait?condition=not-running",
            accept_status=(200,),
        )
        exit_code = wait_resp.get("StatusCode", -1) if wait_resp else -1

        # Retrieve stdout + stderr logs
        raw_logs = _docker_socket_raw(
            "GET",
            f"/containers/{container_id}/logs?stdout=1&stderr=1&tail=1000",
            timeout=float(timeout_secs),
        )
        output = _strip_docker_log_header(raw_logs)
    finally:
        # Always clean up the container
        try:
            _docker_socket_json("DELETE", f"/containers/{container_id}?force=1",
                                accept_status=(200, 204, 404, 409))
        except Exception:
            pass  # best-effort cleanup

    return {
        "status": "success" if exit_code == 0 else "error",
        "command": command,
        "exit_code": exit_code,
        "stdout": output or "(empty)",
        "stderr": "(none)",
        "host": "runtime-control-lv3",
    }


HANDLERS: Final[dict[str, Any]] = {
    "get_platform_status": tool_get_platform_status,
    "list_recent_receipts": tool_list_recent_receipts,
    "get_deployment_history": tool_get_deployment_history,
    "get_workflow_contract": tool_get_workflow_contract,
    "get_command_contract": tool_get_command_contract,
    "get_api_publication_surface": tool_get_api_publication_surface,
    "get_maintenance_windows": tool_get_maintenance_windows,
    "list_serverclaw_skills": tool_list_serverclaw_skills,
    "export_mcp_tools": tool_export_mcp_tools,
    "query_platform_context": tool_query_platform_context,
    "browser_run_session": tool_browser_run_session,
    "check_command_approval": tool_check_command_approval,
    "run_governed_command": tool_run_governed_command,
    "list_containers": tool_list_containers,
    "get_container_logs": tool_get_container_logs,
    "list_nomad_jobs": tool_list_nomad_jobs,
    "get_nomad_job_status": tool_get_nomad_job_status,
    "dispatch_nomad_job": tool_dispatch_nomad_job,
    "list_plane_tasks": tool_list_plane_tasks,
    "get_plane_task": tool_get_plane_task,
    "create_plane_task": tool_create_plane_task,
    "update_plane_task": tool_update_plane_task,
    "add_plane_comment": tool_add_plane_comment,
    "list_outline_collections": tool_list_outline_collections,
    "search_outline_documents": tool_search_outline_documents,
    "get_outline_document": tool_get_outline_document,
    "create_outline_document": tool_create_outline_document,
    "list_outline_documents": tool_list_outline_documents,
    "update_outline_document": tool_update_outline_document,
    "upsert_outline_document": tool_upsert_outline_document,
    "delete_outline_document": tool_delete_outline_document,
    "provision_outline_api_token": tool_provision_outline_api_token,
    "mempalace_search": tool_mempalace_search,
    "mempalace_add_drawer": tool_mempalace_add_drawer,
    "mempalace_wake_up": tool_mempalace_wake_up,
    "mempalace_status": tool_mempalace_status,
    "execute_host_command": tool_execute_host_command,
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
