import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "configure-directus.md"
SERVICE_CAPABILITY_PATH = REPO_ROOT / "config" / "service-capability-catalog.json"
HEALTH_PROBE_PATH = REPO_ROOT / "config" / "health-probe-catalog.json"
REDUNDANCY_PATH = REPO_ROOT / "config" / "service-redundancy-catalog.json"


def test_directus_service_catalog_declares_active_runtime_and_secret_contract() -> None:
    catalog = json.loads(SERVICE_CAPABILITY_PATH.read_text())
    service = next(item for item in catalog["services"] if item["id"] == "directus")

    assert service["lifecycle_status"] == "active"
    assert service["internal_url"] == "http://10.10.10.20:8055"
    assert service["public_url"] == "https://data.lv3.org"
    assert service["subdomain"] == "data.lv3.org"
    assert service["health_probe_id"] == "directus"
    assert service["runbook"] == "docs/runbooks/configure-directus.md"
    assert service["secret_catalog_ids"] == [
        "directus_database_password",
        "directus_key",
        "directus_secret",
        "directus_admin_password",
        "directus_service_registry_token",
        "keycloak_directus_client_secret",
    ]


def test_directus_health_probe_catalog_covers_local_runtime_and_public_health() -> None:
    probes = json.loads(HEALTH_PROBE_PATH.read_text())
    probe = probes["services"]["directus"]

    assert probe["startup"]["url"] == "http://127.0.0.1:8055/server/health"
    assert probe["liveness"]["url"] == "http://127.0.0.1:8055/server/health"
    assert probe["readiness"]["docker_publication"]["container_name"] == "directus"
    assert probe["readiness"]["docker_publication"]["bindings"] == [{"host": "10.10.10.20", "port": 8055}]
    assert probe["readiness"]["docker_publication"]["required_networks"] == ["directus_default"]
    assert probe["uptime_kuma"]["enabled"] is True
    assert probe["uptime_kuma"]["monitor"]["name"] == "Directus Public Health"
    assert probe["uptime_kuma"]["monitor"]["url"] == "https://data.lv3.org/server/health"


def test_directus_runbook_documents_database_boundary_and_public_verification() -> None:
    text = RUNBOOK_PATH.read_text(encoding="utf-8")

    assert "dedicated `directus` database" in text
    assert "`public` schema" in text
    assert "Keycloak" in text
    assert "make converge-directus" in text
    assert "verify-public" in text
    assert "data.lv3.org" in text


def test_directus_redundancy_catalog_declares_cold_standby_recovery() -> None:
    redundancy = json.loads(REDUNDANCY_PATH.read_text())
    service = redundancy["services"]["directus"]

    assert service["tier"] == "R1"
    assert service["backup_sources"] == ["git_repository", "pbs_vm_120", "pbs_vm_130"]
    assert service["standby"]["kind"] == "cold"
    assert service["standby"]["location"] == "docker-runtime-lv3"
