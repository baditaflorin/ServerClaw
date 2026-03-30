from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runbook_documents_private_watch_catalogue_contract() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "configure-changedetection.md").read_text(encoding="utf-8")

    assert "watch catalogue is the source of truth" in runbook
    assert "There is no public DNS record" in runbook
    assert "Mattermost and ntfy" in runbook
    assert "/opt/changedetection/watch-sync-report.json" in runbook
    assert "ops@100.64.0.1" in runbook


def test_playbooks_exist_for_changedetection_service_and_leaf_wrapper() -> None:
    playbook = (REPO_ROOT / "playbooks" / "changedetection.yml").read_text(encoding="utf-8")
    wrapper = (REPO_ROOT / "playbooks" / "services" / "changedetection.yml").read_text(encoding="utf-8")

    assert "service-changedetection" in playbook
    assert "lv3.platform.changedetection_runtime" in playbook
    assert "lv3.platform.api_gateway_runtime" in playbook
    assert "- import_playbook: ../changedetection.yml" in wrapper


def test_service_catalogs_capture_changedetection_runtime_contract() -> None:
    service_catalog = load_json(REPO_ROOT / "config" / "service-capability-catalog.json")
    health_catalog = load_json(REPO_ROOT / "config" / "health-probe-catalog.json")

    service = next(item for item in service_catalog["services"] if item["id"] == "changedetection")
    probe = health_catalog["services"]["changedetection"]

    assert service["internal_url"] == "http://10.10.10.20:5000"
    assert service["exposure"] == "private-only"
    assert service["health_probe_id"] == "changedetection"
    assert service["image_catalog_ids"] == ["changedetection_runtime"]
    assert probe["verify_file"] == "roles/changedetection_runtime/tasks/verify.yml"
    assert "/api/v1/tags" in probe["readiness"]["argv"][2]
    assert probe["uptime_kuma"]["enabled"] is False
