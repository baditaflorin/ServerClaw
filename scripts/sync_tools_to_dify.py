#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from controller_automation_toolkit import load_json, repo_path

from dify_api import DifyClient, read_secret


REGISTRY_PATH = repo_path("config", "agent-tool-registry.json")
DEFAULT_PROVIDER_NAME = "lv3_platform"
DEFAULT_GATEWAY_BASE_URL = "https://api.lv3.org"
DEFAULT_TOOLS_HEADER = "X-LV3-Dify-Api-Key"


def build_openapi_spec(
    registry: dict[str, Any],
    *,
    gateway_base_url: str,
    title: str = "LV3 Platform Governed Tools",
    version: str = "1.0.0",
) -> dict[str, Any]:
    gateway_base_url = gateway_base_url.rstrip("/")
    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": title,
            "version": version,
            "description": "Governed LV3 platform tools published for Dify through the platform API gateway.",
        },
        "servers": [{"url": gateway_base_url}],
        "paths": {},
    }
    for tool in registry.get("tools", []):
        name = tool["name"]
        input_schema = tool.get("input_schema") or {"type": "object", "properties": {}, "additionalProperties": False}
        output_schema = tool.get("output_schema") or {"type": "object"}
        path = f"/v1/dify-tools/{name}"
        spec["paths"][path] = {
            "post": {
                "operationId": name,
                "summary": tool.get("title") or name,
                "description": tool.get("description") or "",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": input_schema}},
                },
                "responses": {
                    "200": {
                        "description": "Tool result",
                        "content": {"application/json": {"schema": output_schema}},
                    }
                },
            }
        }
    return spec


def sync_tool_provider(
    client: DifyClient,
    *,
    provider_name: str,
    gateway_base_url: str,
    tools_api_key: str,
    tools_api_key_header: str = DEFAULT_TOOLS_HEADER,
) -> dict[str, Any]:
    registry = load_json(REGISTRY_PATH)
    schema = build_openapi_spec(registry, gateway_base_url=gateway_base_url)
    credentials = {
        "auth_type": "api_key",
        "api_key_header": tools_api_key_header,
        "api_key_value": tools_api_key,
    }
    existing = client.get_api_tool_provider(provider_name)
    if existing is None:
        result = client.add_api_tool_provider(
            provider_name=provider_name,
            schema=schema,
            credentials=credentials,
            icon={},
            labels=["lv3", "governed"],
            custom_disclaimer="Repo-managed governed LV3 platform tools.",
        )
        action = "created"
    else:
        result = client.update_api_tool_provider(
            provider_name=provider_name,
            schema=schema,
            credentials=credentials,
            icon={},
            labels=["lv3", "governed"],
            custom_disclaimer="Repo-managed governed LV3 platform tools.",
        )
        action = "updated"
    return {
        "action": action,
        "provider_name": provider_name,
        "tool_count": len(registry.get("tools", [])),
        "result": result,
        "schema": schema,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the governed LV3 tool registry into Dify.")
    parser.add_argument("--base-url", required=True, help="Public Dify base URL, for example https://agents.lv3.org")
    parser.add_argument("--admin-email", required=True, help="Dify admin email")
    parser.add_argument("--admin-password-file", required=True, help="Path to the Dify admin password file")
    parser.add_argument("--tools-api-key-file", required=True, help="Path to the Dify tools gateway API key file")
    parser.add_argument("--provider-name", default=DEFAULT_PROVIDER_NAME, help="Dify provider name")
    parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL, help="Platform API gateway base URL")
    parser.add_argument("--tools-api-key-header", default=DEFAULT_TOOLS_HEADER, help="Gateway header name for the Dify API key")
    parser.add_argument("--output-openapi", help="Optional path to write the generated OpenAPI schema")
    args = parser.parse_args()

    client = DifyClient(args.base_url)
    client.login(email=args.admin_email, password=read_secret(args.admin_password_file))
    summary = sync_tool_provider(
        client,
        provider_name=args.provider_name,
        gateway_base_url=args.gateway_base_url,
        tools_api_key=read_secret(args.tools_api_key_file),
        tools_api_key_header=args.tools_api_key_header,
    )
    if args.output_openapi:
        output_path = Path(args.output_openapi).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary["schema"], indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "schema"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
