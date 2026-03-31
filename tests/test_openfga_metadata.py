from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_openfga_service_catalog_distinguishes_runtime_from_controller_proxy() -> None:
    service_catalog = load_json(REPO_ROOT / "config" / "service-capability-catalog.json")
    service = next(item for item in service_catalog["services"] if item["id"] == "openfga")

    assert service["internal_url"] == "http://10.10.10.20:8098"
    assert service["environments"]["production"]["url"] == "http://10.10.10.20:8098"
    assert "http://100.64.0.1:8014" in service["environments"]["production"]["notes"]


def test_openfga_slos_target_guest_reachable_runtime_health_endpoint() -> None:
    slo_catalog = load_json(REPO_ROOT / "config" / "slo-catalog.json")
    openfga_slos = [entry for entry in slo_catalog["slos"] if entry["service_id"] == "openfga"]

    assert {entry["target_url"] for entry in openfga_slos} == {"http://10.10.10.20:8098/healthz"}
    assert any("guest-network" in entry["description"] for entry in openfga_slos)


def test_openfga_runbook_documents_runtime_and_controller_endpoint_split() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "configure-openfga.md").read_text(encoding="utf-8")

    assert "http://10.10.10.20:8098" in runbook
    assert "http://100.64.0.1:8014" in runbook
    assert "canonical guest-network runtime URL" in runbook


def test_openfga_network_policy_allows_controller_build_and_monitoring_access() -> None:
    host_vars = yaml.safe_load((REPO_ROOT / "inventory" / "host_vars" / "proxmox_florin.yml").read_text(encoding="utf-8"))
    rules = host_vars["network_policy"]["guests"]["docker-runtime-lv3"]["allowed_inbound"]

    assert any(rule["source"] == "host" and 8098 in rule["ports"] for rule in rules)
    assert any(rule["source"] == "docker-build-lv3" and 8098 in rule["ports"] for rule in rules)
    assert any(rule["source"] == "monitoring-lv3" and 8098 in rule["ports"] for rule in rules)
