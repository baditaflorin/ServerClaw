import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import typesense_catalog_sync as sync  # noqa: E402


class FakeTypesenseClient:
    def __init__(self, *, collection: dict | None = None, documents: list[dict] | None = None) -> None:
        self.collection = copy.deepcopy(collection)
        self.documents = copy.deepcopy(documents or [])
        self.deleted = False
        self.created_schema: dict | None = None
        self.imported_documents: list[dict] = []

    def get_collection(self, name: str) -> dict | None:
        if self.collection is None:
            return None
        return copy.deepcopy(self.collection)

    def export_documents(self, name: str) -> list[dict]:
        return copy.deepcopy(self.documents)

    def delete_collection(self, name: str) -> None:
        self.deleted = True
        self.collection = None
        self.documents = []

    def create_collection(self, schema: dict) -> None:
        self.created_schema = copy.deepcopy(schema)
        self.collection = {"name": schema["name"], "fields": schema["fields"], "num_documents": 0}

    def import_documents(self, name: str, documents: list[dict]) -> list[dict]:
        self.imported_documents = copy.deepcopy(documents)
        self.documents = copy.deepcopy(documents)
        assert self.collection is not None
        self.collection["num_documents"] = len(documents)
        return [{"success": True, "id": document["id"]} for document in documents]


def test_build_platform_service_documents_normalizes_fields_and_sorts() -> None:
    catalog = {
        "services": [
            {
                "id": "windmill",
                "name": "Windmill",
                "description": "Workflow runtime",
                "category": "automation",
                "lifecycle_status": "active",
                "exposure": "private-only",
                "vm": "docker-runtime-lv3",
                "vmid": 120,
                "internal_url": "http://10.10.10.20:8000",
                "public_url": "",
                "subdomain": "",
                "health_probe_id": "windmill",
                "adr": "0044",
                "runbook": "docs/runbooks/configure-windmill.md",
                "tags": ["workflow", "automation"],
                "environments": {"production": {"url": "http://100.64.0.1:8005"}},
            },
            {
                "id": "api_gateway",
                "name": "Platform API Gateway",
                "description": "Gateway",
                "category": "automation",
                "lifecycle_status": "active",
                "exposure": "edge-published",
                "vm": "docker-runtime-lv3",
                "internal_url": "https://api.lv3.org",
                "public_url": "https://api.lv3.org",
                "subdomain": "api.lv3.org",
                "health_probe_id": "api_gateway",
                "adr": "0092",
                "runbook": "docs/runbooks/configure-api-gateway.md",
                "tags": ["gateway"],
                "environments": {"production": {"url": "https://api.lv3.org"}},
            },
        ]
    }

    documents = sync.build_platform_service_documents(catalog)

    assert [document["id"] for document in documents] == ["api_gateway", "windmill"]
    windmill = next(document for document in documents if document["id"] == "windmill")
    assert windmill["vmid"] == 120
    assert windmill["production_url"] == "http://100.64.0.1:8005"
    assert windmill["tags"] == ["automation", "workflow"]


def test_sync_platform_service_collection_recreates_collection_when_catalog_changes() -> None:
    client = FakeTypesenseClient()
    catalog = {
        "services": [
            {
                "id": "api_gateway",
                "name": "Platform API Gateway",
                "description": "Gateway",
                "category": "automation",
                "lifecycle_status": "active",
                "exposure": "edge-published",
                "vm": "docker-runtime-lv3",
                "internal_url": "https://api.lv3.org",
                "public_url": "https://api.lv3.org",
                "subdomain": "api.lv3.org",
                "health_probe_id": "api_gateway",
                "adr": "0092",
                "runbook": "docs/runbooks/configure-api-gateway.md",
                "tags": ["gateway"],
            }
        ]
    }

    result = sync.sync_platform_service_collection(client, catalog)

    assert result == {
        "changed": True,
        "collection": "platform-services",
        "documents": 1,
        "imported_documents": 1,
    }
    assert client.deleted is False
    assert client.created_schema is not None
    assert client.imported_documents[0]["id"] == "api_gateway"


def test_sync_platform_service_collection_is_noop_when_schema_and_documents_match() -> None:
    desired_documents = sync.normalize_documents(
        sync.build_platform_service_documents(
            {
                "services": [
                    {
                        "id": "api_gateway",
                        "name": "Platform API Gateway",
                        "description": "Gateway",
                        "category": "automation",
                        "lifecycle_status": "active",
                        "exposure": "edge-published",
                        "vm": "docker-runtime-lv3",
                        "internal_url": "https://api.lv3.org",
                        "public_url": "https://api.lv3.org",
                        "subdomain": "api.lv3.org",
                        "health_probe_id": "api_gateway",
                        "adr": "0092",
                        "runbook": "docs/runbooks/configure-api-gateway.md",
                        "tags": ["gateway"],
                    }
                ]
            }
        )
    )
    client = FakeTypesenseClient(
        collection={
            "name": "platform-services",
            "fields": json.loads(json.dumps(sync.PLATFORM_SERVICE_SCHEMA["fields"])),
            "num_documents": 1,
        },
        documents=desired_documents,
    )

    result = sync.sync_platform_service_collection(
        client,
        {
            "services": [
                {
                    "id": "api_gateway",
                    "name": "Platform API Gateway",
                    "description": "Gateway",
                    "category": "automation",
                    "lifecycle_status": "active",
                    "exposure": "edge-published",
                    "vm": "docker-runtime-lv3",
                    "internal_url": "https://api.lv3.org",
                    "public_url": "https://api.lv3.org",
                    "subdomain": "api.lv3.org",
                    "health_probe_id": "api_gateway",
                    "adr": "0092",
                    "runbook": "docs/runbooks/configure-api-gateway.md",
                    "tags": ["gateway"],
                }
            ]
        },
    )

    assert result["changed"] is False
    assert client.deleted is False
    assert client.created_schema is None
    assert client.imported_documents == []
