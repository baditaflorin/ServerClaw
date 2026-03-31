import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import api_gateway_catalog  # noqa: E402


def test_gateway_catalog_validates() -> None:
    catalog, normalized = api_gateway_catalog.load_api_gateway_catalog()

    assert catalog["schema_version"] == "1.0.0"
    assert normalized
    assert any(service["id"] == "windmill" for service in normalized)


def test_duplicate_gateway_prefix_fails() -> None:
    catalog, _normalized = api_gateway_catalog.load_api_gateway_catalog()
    broken = copy.deepcopy(catalog)
    broken["services"][0]["gateway_prefix"] = broken["services"][1]["gateway_prefix"]

    try:
        api_gateway_catalog.validate_api_gateway_catalog(broken)
    except ValueError as exc:
        assert "duplicate gateway prefix" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected duplicate gateway prefix failure")


def test_typesense_route_uses_raw_header_auth_contract() -> None:
    _catalog, normalized = api_gateway_catalog.load_api_gateway_catalog()
    route = next(service for service in normalized if service["id"] == "typesense")

    assert route["upstream_auth_env_var"] == "LV3_GATEWAY_TYPESENSE_API_KEY"
    assert route["upstream_auth_header"] == "X-TYPESENSE-API-KEY"
    assert route["upstream_auth_scheme"] == "raw"
