from __future__ import annotations

from scripts.sync_tools_to_dify import build_openapi_spec


def test_build_openapi_spec_creates_one_path_per_governed_tool() -> None:
    registry = {
        "tools": [
            {
                "name": "get-platform-status",
                "title": "Get Platform Status",
                "description": "Read the current platform state.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                "output_schema": {"type": "object", "properties": {"repo_version": {"type": "string"}}},
            },
            {
                "name": "list-recent-receipts",
                "title": "List Recent Receipts",
                "description": "List recent receipts.",
                "input_schema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1}},
                    "additionalProperties": False,
                },
                "output_schema": {"type": "object", "properties": {"count": {"type": "integer"}}},
            },
        ]
    }

    spec = build_openapi_spec(registry, gateway_base_url="https://api.example.com")

    assert spec["servers"] == [{"url": "https://api.example.com"}]
    assert "/v1/dify-tools/get-platform-status" in spec["paths"]
    assert "/v1/dify-tools/list-recent-receipts" in spec["paths"]
    assert spec["paths"]["/v1/dify-tools/list-recent-receipts"]["post"]["operationId"] == "list-recent-receipts"
    assert (
        spec["paths"]["/v1/dify-tools/list-recent-receipts"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["properties"]["limit"]["minimum"]
        == 1
    )
