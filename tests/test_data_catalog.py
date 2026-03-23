from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


data_catalog = load_module("data_catalog", "scripts/data_catalog.py")
decommission_service = load_module("decommission_service", "scripts/decommission_service.py")


def test_data_catalog_validates_current_repo_payload() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "data-catalog.json").read_text(encoding="utf-8"))
    data_catalog.validate_data_catalog(catalog)


def test_data_catalog_rejects_public_secret_store() -> None:
    invalid = {
        "$schema": "docs/schema/data-catalog.schema.json",
        "schema_version": "1.0.0",
        "data_stores": [
            {
                "id": "secrets",
                "service": "openbao",
                "name": "Secrets",
                "class": "secret",
                "retention_days": None,
                "backup_included": True,
                "access_role": "public",
                "pii_risk": "low",
                "locations": ["kv/app"],
                "notes": "invalid"
            }
        ]
    }

    try:
        data_catalog.validate_data_catalog(invalid)
    except ValueError as exc:
        assert "must not be public for secret data stores" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected validation to fail")


def test_netbox_decommission_plan_targets_catalog_and_database() -> None:
    plan = decommission_service.build_plan("netbox")

    assert plan["service_id"] == "netbox"
    assert plan["database_name"] == "netbox"
    assert isinstance(plan["subdomains"], list)
    assert plan["openbao_policy_name"] == "lv3-service-netbox-runtime"
