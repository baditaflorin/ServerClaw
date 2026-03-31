from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_runbook_documents_private_runtime_contract() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "configure-crawl4ai.md").read_text(encoding="utf-8")

    assert "There is no public DNS record" in runbook
    assert "10.10.10.20:11235" in runbook
    assert "/etc/lv3/crawl4ai/config.yml" in runbook
    assert "/monitor/health" in runbook
    assert "coolify-lv3" in runbook


def test_playbooks_exist_for_crawl4ai_service_and_leaf_wrapper() -> None:
    playbook = (REPO_ROOT / "playbooks" / "crawl4ai.yml").read_text(encoding="utf-8")
    wrapper = (REPO_ROOT / "playbooks" / "services" / "crawl4ai.yml").read_text(encoding="utf-8")

    assert "service-crawl4ai" in playbook
    assert "lv3.platform.crawl4ai_runtime" in playbook
    assert "- import_playbook: ../crawl4ai.yml" in wrapper


def test_service_catalogs_capture_crawl4ai_runtime_contract() -> None:
    service_catalog = load_json(REPO_ROOT / "config" / "service-capability-catalog.json")
    health_catalog = load_json(REPO_ROOT / "config" / "health-probe-catalog.json")

    service = next(item for item in service_catalog["services"] if item["id"] == "crawl4ai")
    probe = health_catalog["services"]["crawl4ai"]

    assert service["internal_url"] == "http://10.10.10.20:11235"
    assert service["exposure"] == "private-only"
    assert service["health_probe_id"] == "crawl4ai"
    assert service["image_catalog_ids"] == ["crawl4ai_runtime"]
    assert probe["verify_file"] == "roles/crawl4ai_runtime/tasks/verify.yml"
    assert probe["startup"]["url"] == "http://127.0.0.1:11235/health"
    assert "/monitor/health" in probe["readiness"]["argv"][2]
    assert probe["uptime_kuma"]["enabled"] is False
