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


def test_reference_deployment_sources_validate() -> None:
    module = load_module("reference_deployment_samples_validate", "scripts/reference_deployment_samples.py")

    module.validate_reference_deployment_sources()


def test_render_reference_deployment_sample_writes_expected_files(tmp_path: Path) -> None:
    module = load_module("reference_deployment_samples_render", "scripts/reference_deployment_samples.py")

    rendered_paths = module.render_reference_deployment_sample(
        "single-node-proxmox-lab",
        "dedicated-public-edge",
        output_dir=tmp_path,
    )

    rendered_relative = {path.relative_to(tmp_path).as_posix() for path in rendered_paths}
    assert "inventory/hosts.yml" in rendered_relative
    assert "inventory/host_vars/reference-proxmox.yml" in rendered_relative
    assert "config/api-publication.json" in rendered_relative
    assert ".local/reference-deployment/controller-local-secrets.json" in rendered_relative
    manifest = json.loads((tmp_path / ".reference-deployment-render.json").read_text(encoding="utf-8"))
    assert manifest["sample_id"] == "single-node-proxmox-lab"
    assert manifest["provider_profile_id"] == "dedicated-public-edge"


def test_validate_provider_profile_catalog_rejects_absolute_overlay_root() -> None:
    module = load_module("reference_deployment_samples_profile_validation", "scripts/reference_deployment_samples.py")
    catalog_path = REPO_ROOT / "config" / "reference-provider-profiles.yaml"

    payload = {
        "schema_version": "1.0.0",
        "profiles": [
            {
                "id": "bad-profile",
                "title": "Bad profile",
                "description": "Bad",
                "values": {key: "value" for key in module.REQUIRED_PROFILE_VALUE_KEYS},
            }
        ],
    }
    payload["profiles"][0]["values"].update(
        {
            "sample_proxmox_management_ipv4": "203.0.113.10",
            "sample_proxmox_management_gateway4": "203.0.113.1",
            "sample_proxmox_management_tailscale_ipv4": "100.64.10.1",
            "sample_internal_gateway_ipv4": "10.42.0.1",
            "sample_internal_network_cidr": "10.42.0.0/24",
            "sample_public_edge_ipv4": "10.42.0.10",
            "sample_runtime_ipv4": "10.42.0.20",
            "sample_public_base_domain": "apps.example.test",
            "sample_operator_base_domain": "private.example.test",
            "sample_public_edge_hostname": "edge.apps.example.test",
            "sample_proxmox_api_url": "https://proxmox.private.example.test:8006/api2/json",
            "sample_requester_email": "ops@example.test",
            "sample_overlay_root": "/tmp/not-allowed",
        }
    )

    try:
        module.validate_provider_profile_catalog(payload, path=catalog_path)
    except ValueError as exc:
        assert ".local/" in str(exc)
    else:
        raise AssertionError("expected validate_provider_profile_catalog to reject an absolute overlay root")
