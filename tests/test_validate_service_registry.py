from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_service_registry as registry_validator


def test_check_accepts_current_service_type_variants() -> None:
    registry = {
        "platform_service_registry": {
            "directus": {
                "service_type": "docker_compose",
                "image_catalog_key": "directus_runtime",
                "internal_port": 8055,
                "host_group": "docker-runtime",
            },
            "alertmanager": {
                "service_type": "system_package",
                "image_catalog_key": "alertmanager_runtime",
                "internal_port": 9093,
                "host_group": "monitoring",
                "state_dirs": {
                    "config": "/etc/alertmanager",
                    "data": "/var/lib/prometheus/alertmanager",
                    "secrets": "/etc/alertmanager",
                },
            },
            "docker_runtime": {
                "service_type": "infrastructure",
                "image_catalog_key": "docker_runtime",
                "internal_port": None,
                "host_group": "all",
            },
            "nginx_runtime": {
                "service_type": "system_package",
                "image_catalog_key": "nginx_runtime",
                "internal_port": None,
                "host_group": "all",
                "state_dirs": {
                    "config": "/etc/nginx",
                    "data": "/var/cache/nginx",
                    "secrets": "/etc/lv3/nginx",
                },
            },
            "neko": {
                "service_type": "multi_instance",
                "image_catalog_key": "neko_runtime",
                "internal_port": 8080,
                "host_group": "runtime-comms",
            },
        }
    }
    image_catalog = {"directus_runtime": {}}
    runtime_roles = [
        "alertmanager_runtime",
        "directus_runtime",
        "docker_runtime",
        "nginx_runtime",
        "neko_runtime",
    ]
    inventory_names = {"all", "docker-runtime", "monitoring", "runtime-comms"}

    errors, warnings = registry_validator.check(registry, image_catalog, runtime_roles, inventory_names)

    assert errors == []
    assert warnings == []


def test_check_rejects_invalid_docker_service_contract() -> None:
    registry = {
        "platform_service_registry": {
            "broken": {
                "service_type": "docker_compose",
                "image_catalog_key": "missing_image",
                "internal_port": None,
                "host_group": "missing-host",
            }
        }
    }

    errors, warnings = registry_validator.check(
        registry,
        image_catalog={"directus_runtime": {}},
        runtime_roles=[],
        inventory_names={"all", "docker-runtime"},
    )

    assert warnings == []
    assert any("image_catalog_key 'missing_image' not found" in error for error in errors)
    assert any("internal_port must be an integer" in error for error in errors)
    assert any("host_group 'missing-host' not found in inventory hosts/groups" in error for error in errors)


def test_load_registry_file_rejects_duplicate_keys(tmp_path: Path) -> None:
    registry_path = tmp_path / "platform_services.yml"
    registry_path.write_text(
        """
platform_service_registry:
  demo:
    service_type: docker_compose
    internal_port: 1234
    host_group: docker-runtime
    service_type: infrastructure
""".strip()
        + "\n",
        encoding="utf-8",
    )

    try:
        registry_validator.load_registry_file(registry_path)
    except ValueError as exc:
        assert "Duplicate key 'service_type'" in str(exc)
    else:
        raise AssertionError("expected duplicate key validation to fail")


def test_repo_intake_port_does_not_conflict_with_browser_runner() -> None:
    registry = registry_validator.load_registry()
    service_map = registry["platform_service_registry"]

    assert service_map["repo_intake"]["internal_port"] != service_map["browser_runner"]["internal_port"]
