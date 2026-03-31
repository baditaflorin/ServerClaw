import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "directus_bootstrap.py"


def load_script_module():
    spec = spec_from_file_location("directus_bootstrap", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ensure_collection_uses_collection_listing_before_create() -> None:
    module = load_script_module()
    calls: list[tuple[str, str, dict | None]] = []

    def fake_api_request(opener, base_url, method, path, *, token=None, body=None, **kwargs):
        calls.append((method, path, body))
        if method == "GET" and path == "/collections":
            return {"data": []}
        if method == "POST" and path == "/collections":
            return {"data": {"collection": "service_registry"}}
        raise AssertionError(f"unexpected call: {(method, path)}")

    module.api_request = fake_api_request

    changed = module.ensure_collection(object(), "http://127.0.0.1:8055", "token", "service_registry")

    assert changed is True
    assert calls == [
        ("GET", "/collections", None),
        (
            "POST",
            "/collections",
            {
                "collection": "service_registry",
                "meta": {
                    "icon": "storage",
                    "note": "Repo-managed Directus service registry collection.",
                },
                "schema": {"name": "service_registry"},
            },
        ),
    ]


def test_ensure_field_uses_field_listing_before_create() -> None:
    module = load_script_module()
    calls: list[tuple[str, str, dict | None]] = []
    spec = module.FieldSpec(
        name="service_name",
        type="string",
        data_type="varchar",
        required=True,
        interface="input",
        note="Stable service identifier.",
        max_length=255,
    )

    def fake_api_request(opener, base_url, method, path, *, token=None, body=None, **kwargs):
        calls.append((method, path, body))
        if method == "GET" and path == "/fields/service_registry":
            return {"data": []}
        if method == "POST" and path == "/fields/service_registry":
            return {"data": {"field": "service_name"}}
        raise AssertionError(f"unexpected call: {(method, path)}")

    module.api_request = fake_api_request

    changed = module.ensure_field(object(), "http://127.0.0.1:8055", "token", "service_registry", spec)

    assert changed is True
    assert calls == [
        ("GET", "/fields/service_registry", None),
        (
            "POST",
            "/fields/service_registry",
            {
                "field": "service_name",
                "type": "string",
                "schema": {
                    "name": "service_name",
                    "table": "service_registry",
                    "data_type": "varchar",
                    "is_nullable": False,
                    "max_length": 255,
                },
                "meta": {
                    "interface": "input",
                    "required": True,
                    "width": "half",
                    "note": "Stable service identifier.",
                },
            },
        ),
    ]
