#!/usr/bin/env python3
"""Generate grouped OpenAPI specs for LibreChat agent tool packs.

Each agent gets a focused subset of tools from the platform registry,
keeping context window usage reasonable (5-8 tools per spec).

Usage:
    python3 scripts/generate_librechat_tool_specs.py --write
    python3 scripts/generate_librechat_tool_specs.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "config" / "agent-tool-registry.json"
OUTPUT_DIR = REPO_ROOT / "build" / "librechat-tools"

# Tool packs: each maps to a LibreChat agent
TOOL_PACKS = {
    "ops": {
        "title": "ServerClaw Ops — Infrastructure Observability",
        "description": "Platform status, container listing, logs, deployment history, and maintenance windows.",
        "tools": [
            "get-platform-status",
            "list-containers",
            "get-container-logs",
            "list-recent-receipts",
            "get-deployment-history",
            "get-maintenance-windows",
            "query-platform-context",
        ],
    },
    "tasks": {
        "title": "ServerClaw Tasks — Project Management",
        "description": "Create, view, update Plane tasks and comments for project tracking.",
        "tools": [
            "list-plane-tasks",
            "get-plane-task",
            "create-plane-task",
            "update-plane-task",
            "add-plane-comment",
        ],
    },
    "docs": {
        "title": "ServerClaw Docs — Knowledge Base",
        "description": "Search, read, and manage Outline wiki documents and collections.",
        "tools": [
            "list-outline-collections",
            "list-outline-documents",
            "search-outline-documents",
            "get-outline-document",
            "create-outline-document",
            "update-outline-document",
            "upsert-outline-document",
        ],
    },
    "admin": {
        "title": "ServerClaw Admin — Governed Operations",
        "description": "Execute governed commands, manage Nomad jobs, approval workflows. Requires elevated access.",
        "tools": [
            "run-governed-command",
            "check-command-approval",
            "get-workflow-contract",
            "get-command-contract",
            "list-nomad-jobs",
            "get-nomad-job-status",
            "dispatch-nomad-job",
            "get-api-publication-surface",
        ],
    },
    "memory": {
        "title": "ServerClaw Memory — Cross-Session Knowledge",
        "description": "Search and save memories from prior agent sessions. 4,681+ indexed memories from ADRs, runbooks, and operational insights.",
        "tools": [
            "mempalace-search",
            "mempalace-add-drawer",
            "mempalace-wake-up",
            "mempalace-status",
        ],
    },
}

GATEWAY_BASE_URL = "http://10.10.10.92:8083"
AUTH_HEADER = "X-LV3-Dify-Api-Key"


def build_pack_spec(
    pack_id: str,
    pack_meta: dict,
    tools_by_name: dict,
) -> dict:
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": pack_meta["title"],
            "version": "1.0.0",
            "description": pack_meta["description"],
        },
        "servers": [{"url": GATEWAY_BASE_URL}],
        "paths": {},
        "components": {
            "securitySchemes": {
                "apiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": AUTH_HEADER,
                }
            }
        },
        "security": [{"apiKey": []}],
    }

    for tool_name in pack_meta["tools"]:
        tool = tools_by_name.get(tool_name)
        if not tool:
            print(f"  WARNING: tool '{tool_name}' in pack '{pack_id}' not found in registry", file=sys.stderr)
            continue

        input_schema = tool.get("input_schema") or {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        output_schema = tool.get("output_schema") or {"type": "object"}

        spec["paths"][f"/v1/dify-tools/{tool_name}"] = {
            "post": {
                "operationId": tool_name,
                "summary": tool.get("title") or tool_name,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write specs to build/librechat-tools/")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    args = parser.parse_args()

    registry = json.loads(REGISTRY_PATH.read_text())
    tools_by_name = {t["name"]: t for t in registry.get("tools", [])}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate per-pack specs
    for pack_id, pack_meta in TOOL_PACKS.items():
        spec = build_pack_spec(pack_id, pack_meta, tools_by_name)
        tool_count = len(spec["paths"])
        out_file = OUTPUT_DIR / f"{pack_id}.openapi.json"

        if args.dry_run or not args.write:
            print(f"  {pack_id}: {tool_count} tools -> {out_file}")
        if args.write:
            out_file.write_text(json.dumps(spec, indent=2) + "\n")
            print(f"  wrote {out_file} ({tool_count} tools)")

    # Also generate the combined "all tools" spec
    all_spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "LV3 Platform Tools (All)",
            "version": "1.0.0",
            "description": "All governed LV3 platform tools. Use deferred_tools for context-efficient discovery.",
        },
        "servers": [{"url": GATEWAY_BASE_URL}],
        "paths": {},
        "components": {
            "securitySchemes": {
                "apiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": AUTH_HEADER,
                }
            }
        },
        "security": [{"apiKey": []}],
    }
    for tool in registry.get("tools", []):
        name = tool["name"]
        input_schema = tool.get("input_schema") or {"type": "object", "properties": {}, "additionalProperties": False}
        output_schema = tool.get("output_schema") or {"type": "object"}
        all_spec["paths"][f"/v1/dify-tools/{name}"] = {
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
    out_file = OUTPUT_DIR / "all.openapi.json"
    if args.dry_run or not args.write:
        print(f"  all: {len(all_spec['paths'])} tools -> {out_file}")
    if args.write:
        out_file.write_text(json.dumps(all_spec, indent=2) + "\n")
        print(f"  wrote {out_file} ({len(all_spec['paths'])} tools)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
