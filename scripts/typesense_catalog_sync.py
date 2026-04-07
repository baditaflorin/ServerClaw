#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from validation_toolkit import require_list, require_mapping


DEFAULT_COLLECTION = "platform-services"
PLATFORM_SERVICE_SCHEMA = {
    "name": DEFAULT_COLLECTION,
    "fields": [
        {"name": "id", "type": "string"},
        {"name": "name", "type": "string"},
        {"name": "description", "type": "string"},
        {"name": "category", "type": "string", "facet": True},
        {"name": "lifecycle_status", "type": "string", "facet": True},
        {"name": "exposure", "type": "string", "facet": True},
        {"name": "vm", "type": "string", "facet": True},
        {"name": "vmid", "type": "int32", "optional": True},
        {"name": "internal_url", "type": "string", "optional": True},
        {"name": "public_url", "type": "string", "optional": True},
        {"name": "production_url", "type": "string", "optional": True},
        {"name": "subdomain", "type": "string", "optional": True, "facet": True},
        {"name": "health_probe_id", "type": "string", "optional": True, "facet": True},
        {"name": "adr", "type": "string", "facet": True},
        {"name": "runbook", "type": "string"},
        {"name": "tags", "type": "string[]", "facet": True},
    ],
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_platform_service_documents(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    services = require_list(catalog.get("services"), "config/service-capability-catalog.json.services")
    documents: list[dict[str, Any]] = []
    for index, service in enumerate(services):
        service = require_mapping(service, f"service-capability-catalog.services[{index}]")
        environments = service.get("environments", {})
        production = environments.get("production", {}) if isinstance(environments, dict) else {}
        production = production if isinstance(production, dict) else {}

        document: dict[str, Any] = {
            "id": require_string(service.get("id"), f"service-capability-catalog.services[{index}].id"),
            "name": require_string(service.get("name"), f"service-capability-catalog.services[{index}].name"),
            "description": optional_string(service.get("description")),
            "category": optional_string(service.get("category")),
            "lifecycle_status": optional_string(service.get("lifecycle_status")),
            "exposure": optional_string(service.get("exposure")),
            "vm": optional_string(service.get("vm")),
            "internal_url": optional_string(service.get("internal_url")),
            "public_url": optional_string(service.get("public_url")),
            "production_url": optional_string(production.get("url")),
            "subdomain": optional_string(service.get("subdomain")),
            "health_probe_id": optional_string(service.get("health_probe_id")),
            "adr": optional_string(service.get("adr")),
            "runbook": optional_string(service.get("runbook")),
            "tags": sorted(
                str(tag).strip()
                for tag in service.get("tags", [])
                if isinstance(tag, str) and str(tag).strip()
            ),
        }
        vmid = service.get("vmid")
        if isinstance(vmid, int) and not isinstance(vmid, bool):
            document["vmid"] = vmid
        documents.append(document)
    return sorted(documents, key=lambda item: item["id"])


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "name": schema.get("name"),
        "fields": sorted(
            [
                {
                    key: value
                    for key, value in require_mapping(field, "typesense schema field").items()
                    if key in {"name", "type", "facet", "optional"}
                }
                for field in require_list(schema.get("fields"), "typesense schema fields")
            ],
            key=lambda item: str(item["name"]),
        ),
    }
    return normalized


def normalize_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [{key: value for key, value in document.items() if value not in ("", [], None)} for document in documents],
        key=lambda item: item["id"],
    )


class TypesenseAdminClient:
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        params: dict[str, str] | None = None,
        content_type: str = "application/json",
    ) -> tuple[int, bytes]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = {"X-TYPESENSE-API-KEY": self.api_key}
        if body is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            if exc.code == 404:
                return exc.code, payload
            detail = payload.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Typesense {method} {path} failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Unable to reach Typesense at {self.base_url}: {exc.reason}") from exc

    def get_collection(self, name: str) -> dict[str, Any] | None:
        status, payload = self._request("GET", f"/collections/{name}")
        if status == 404:
            return None
        return require_mapping(json.loads(payload.decode("utf-8")), "typesense collection payload")

    def export_documents(self, name: str) -> list[dict[str, Any]]:
        status, payload = self._request("GET", f"/collections/{name}/documents/export")
        if status == 404:
            return []
        lines = payload.decode("utf-8").splitlines()
        documents = [require_mapping(json.loads(line), "typesense document") for line in lines if line.strip()]
        return sorted(documents, key=lambda item: str(item["id"]))

    def delete_collection(self, name: str) -> None:
        status, _payload = self._request("DELETE", f"/collections/{name}")
        if status not in {200, 204, 404}:
            raise RuntimeError(f"Unexpected Typesense status while deleting collection {name}: {status}")

    def create_collection(self, schema: dict[str, Any]) -> None:
        self._request("POST", "/collections", body=json.dumps(schema, sort_keys=True).encode("utf-8"))

    def import_documents(self, name: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not documents:
            return []
        payload = "\n".join(json.dumps(document, sort_keys=True) for document in documents).encode("utf-8")
        _status, body = self._request(
            "POST",
            f"/collections/{name}/documents/import",
            body=payload,
            params={"action": "upsert"},
            content_type="text/plain",
        )
        return [json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()]


def sync_platform_service_collection(
    client: TypesenseAdminClient,
    catalog: dict[str, Any],
    *,
    collection: str = DEFAULT_COLLECTION,
) -> dict[str, Any]:
    schema = dict(PLATFORM_SERVICE_SCHEMA)
    schema["name"] = collection
    desired_documents = build_platform_service_documents(catalog)
    desired_schema = normalize_schema(schema)
    existing_collection = client.get_collection(collection)
    existing_schema = normalize_schema(existing_collection) if existing_collection else None
    existing_documents = normalize_documents(client.export_documents(collection)) if existing_collection else []
    normalized_documents = normalize_documents(desired_documents)

    changed = existing_schema != desired_schema or existing_documents != normalized_documents
    if changed:
        if existing_collection is not None:
            client.delete_collection(collection)
        client.create_collection(schema)
        import_results = client.import_documents(collection, desired_documents)
        failures = [item for item in import_results if not item.get("success")]
        if failures:
            raise RuntimeError(f"Typesense import reported failures: {json.dumps(failures, indent=2)}")
    collection_payload = client.get_collection(collection)
    if collection_payload is None:
        raise RuntimeError(f"Typesense collection {collection!r} was not available after sync")

    imported_count = int(collection_payload.get("num_documents", 0))
    return {
        "changed": changed,
        "collection": collection,
        "documents": len(desired_documents),
        "imported_documents": imported_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync the Typesense platform-services collection from the service catalog.")
    parser.add_argument("--catalog", type=Path, required=True, help="Path to config/service-capability-catalog.json")
    parser.add_argument("--typesense-url", required=True, help="Typesense base URL, for example http://100.64.0.1:8016")
    parser.add_argument("--api-key-file", type=Path, required=True, help="Controller-local file containing the Typesense API key")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Typesense collection name to manage")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = require_mapping(load_json(args.catalog), str(args.catalog))
    api_key = require_string(args.api_key_file.read_text(encoding="utf-8"), str(args.api_key_file))
    client = TypesenseAdminClient(base_url=args.typesense_url, api_key=api_key)
    result = sync_platform_service_collection(client, catalog, collection=args.collection)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
