from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_CATALOG_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
PARTITION_CATALOG_PATH = REPO_ROOT / "config" / "contracts" / "service-partitions" / "catalog.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_service_declares_runtime_partition_metadata() -> None:
    catalog = load_json(SERVICE_CATALOG_PATH)

    for service in catalog["services"]:
        assert service["runtime_pool"]
        assert service["deployment_surface"]
        assert service["restart_domain"]
        assert service["api_contract_ref"]
        assert service["mobility_tier"] in {
            "anchor",
            "movable_singleton",
            "elastic_stateless",
            "burst_batch",
        }


def test_partition_catalog_and_service_catalog_stay_in_sync() -> None:
    catalog = load_json(SERVICE_CATALOG_PATH)
    partition_catalog = load_json(PARTITION_CATALOG_PATH)

    service_ids = {service["id"] for service in catalog["services"]}
    partition_members = {
        service_id
        for partition in partition_catalog["partitions"].values()
        for service_id in partition["services"]
    }

    assert partition_members == service_ids

    for service in catalog["services"]:
        deployment_surface = REPO_ROOT / service["deployment_surface"]
        api_contract_path = REPO_ROOT / service["api_contract_ref"].split("#", 1)[0]

        assert deployment_surface.exists(), service["id"]
        assert api_contract_path.exists(), service["id"]
