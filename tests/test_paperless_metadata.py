from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runbook_documents_public_archive_contract_and_hostname_choice() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "configure-paperless.md").read_text(encoding="utf-8")

    assert "docs.lv3.org remains the developer portal" in runbook
    assert "paperless.lv3.org" in runbook
    assert "OpenBao" in runbook
    assert "smoke-upload-report.json" in runbook
    assert "docker-runtime-lv3" in runbook
    assert "proxmox_guest_ssh_connection_mode=proxmox_host_jump" in runbook


def test_service_catalogs_capture_paperless_runtime_contract() -> None:
    service_catalog = load_json(REPO_ROOT / "config" / "service-capability-catalog.json")
    health_catalog = load_json(REPO_ROOT / "config" / "health-probe-catalog.json")
    image_catalog = load_json(REPO_ROOT / "config" / "image-catalog.json")

    service = next(item for item in service_catalog["services"] if item["id"] == "paperless")
    probe = health_catalog["services"]["paperless"]
    image = image_catalog["images"]["paperless_runtime"]

    assert service["internal_url"] == "http://10.10.10.20:8018"
    assert service["public_url"] == "https://paperless.lv3.org"
    assert service["subdomain"] == "paperless.lv3.org"
    assert service["health_probe_id"] == "paperless"
    assert "paperless_runtime" in service["image_catalog_ids"]
    assert "paperless_api_token" in service["secret_catalog_ids"]
    assert probe["verify_file"] == "roles/paperless_runtime/tasks/verify.yml"
    assert probe["uptime_kuma"]["enabled"] is True
    assert image["registry_ref"] == "ghcr.io/paperless-ngx/paperless-ngx"
    assert image["tag"] == "2.20.4"


def test_subdomain_and_certificate_catalogs_reserve_the_paperless_public_surface() -> None:
    subdomains = load_json(REPO_ROOT / "config" / "subdomain-catalog.json")["subdomains"]
    certificates = load_json(REPO_ROOT / "config" / "certificate-catalog.json")["certificates"]

    subdomain = next(item for item in subdomains if item["fqdn"] == "paperless.lv3.org")
    certificate = next(item for item in certificates if item["service_id"] == "paperless")

    assert subdomain["owner_adr"] == "0285"
    assert subdomain["auth_requirement"] == "upstream_auth"
    assert subdomain["tls"]["provider"] == "letsencrypt"
    assert certificate["endpoint"]["host"] == "paperless.lv3.org"
    assert certificate["expected_issuer"] == "letsencrypt"
