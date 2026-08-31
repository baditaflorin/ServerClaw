from __future__ import annotations

import importlib.util
import json
import subprocess
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


decommission_service = load_module("decommission_service", "scripts/decommission_service.py")
platform_ops = load_module("platform_ops", "scripts/platform_ops.py")


def test_decommission_plan_uses_service_id_subdomain_catalog() -> None:
    plan = decommission_service.build_plan("authentik")

    assert "id.example.com" in plan["subdomains"]
    assert plan["authentik_oauth_client"] is None


def test_rewrite_subdomain_catalog_removes_service_id_and_legacy_service_keys(tmp_path: Path) -> None:
    catalog_path = tmp_path / "subdomain-catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "subdomains": [
                    {"service_id": "authentik", "fqdn": "id.example.com"},
                    {"service": "legacy_service", "hostname": "legacy.example.com"},
                    {"service_id": "grafana", "fqdn": "grafana.example.com"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert decommission_service.rewrite_subdomain_catalog("authentik", catalog_path) is True
    assert decommission_service.rewrite_subdomain_catalog("legacy_service", catalog_path) is True

    remaining = json.loads(catalog_path.read_text(encoding="utf-8"))["subdomains"]
    assert remaining == [{"service_id": "grafana", "fqdn": "grafana.example.com"}]


def test_registry_validation_does_not_warn_for_absent_optional_catalog_entries() -> None:
    assert decommission_service.validate_catalog_registry("netbox") == []


def test_validate_registry_cli_keeps_stdout_machine_readable_json() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/decommission_service.py"),
            "--service",
            "browser_runner",
            "--validate-registry",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["registry_warnings"] == []
    assert "Registry OK" in completed.stderr


def test_decommission_preview_includes_https_tls_marker_files() -> None:
    marker_files = {item["file"] for item in platform_ops._find_yaml_marker_files("authentik")}

    assert "config/prometheus/file_sd/https_tls_targets.yml" in marker_files
    if (REPO_ROOT / "config/prometheus/rules/https_tls_alerts.yml").is_file():
        assert "config/prometheus/rules/https_tls_alerts.yml" in marker_files


def test_authentik_oauth_client_mapping_and_manifest_removal_are_service_scoped(tmp_path: Path) -> None:
    registry_path = tmp_path / "platform_services.yml"
    registry_path.write_text(
        """platform_service_registry:
  # BEGIN SERVICE: grafana
  grafana:
    sso:
      enabled: true
      provider: authentik
      client_id: grafana-oauth
  # END SERVICE: grafana
""",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "oauth-clients.yaml"
    manifest_path.write_text(
        """version: 1
clients:
  - id: grafana-oauth
    application:
      name: Grafana
      slug: grafana
    provider:
      name: grafana-oauth
      client_id: grafana-oauth
  - id: outline
    application:
      name: Outline
      slug: outline
    provider:
      name: outline
      client_id: outline
""",
        encoding="utf-8",
    )

    client = decommission_service.find_authentik_oauth_client(
        "grafana",
        service_registry_path=registry_path,
        manifest_path=manifest_path,
    )

    assert client == {
        "manifest_id": "grafana-oauth",
        "provider_client_id": "grafana-oauth",
        "application_slug": "grafana",
    }
    assert (
        decommission_service._remove_authentik_oauth_manifest_client(
            manifest_path,
            "grafana",
            service_registry_path=registry_path,
        )
        is True
    )
    remaining = manifest_path.read_text(encoding="utf-8")
    assert "id: grafana-oauth" not in remaining
    assert "id: outline" in remaining


def test_delete_authentik_oauth_client_removes_application_before_provider(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def list_all(_base_url: str, _token: str, path: str):
        if path == "/api/v3/providers/oauth2/":
            return [{"pk": 42, "client_id": "grafana-oauth"}]
        assert path == "/api/v3/core/applications/"
        return [{"slug": "grafana", "provider": 42}]

    def request(_base_url: str, _token: str, method: str, path: str):
        calls.append((method, path))
        return {}

    monkeypatch.setattr(decommission_service, "_authentik_list_all", list_all)
    monkeypatch.setattr(decommission_service, "_authentik_api_request", request)

    decommission_service.delete_authentik_oauth_client(
        "https://id.example.com",
        "not-a-real-token",
        {"provider_client_id": "grafana-oauth", "application_slug": "grafana"},
    )

    assert calls == [
        ("DELETE", "/api/v3/core/applications/grafana/"),
        ("DELETE", "/api/v3/providers/oauth2/42/"),
    ]
