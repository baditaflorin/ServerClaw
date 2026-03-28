from __future__ import annotations

import json
from pathlib import Path

from platform.faults import build_network_impairment_report, load_network_impairment_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_network_impairment_matrix_resolves_catalog() -> None:
    catalog = load_network_impairment_matrix(REPO_ROOT / "config" / "network-impairment-matrix.yaml")

    assert "staging" in catalog.target_classes
    assert "added_latency" in catalog.impairments
    assert {entry.service for entry in catalog.entries} == {"api_gateway", "openbao", "windmill"}
    gateway_keycloak = next(entry for entry in catalog.entries if entry.service == "api_gateway" and entry.dependency == "keycloak")
    assert gateway_keycloak.expected_behaviour == "degrade_gracefully"
    assert gateway_keycloak.service_catalog_tested_by == "fault:keycloak-unavailable"


def test_build_network_impairment_report_filters_target_class() -> None:
    catalog = load_network_impairment_matrix(REPO_ROOT / "config" / "network-impairment-matrix.yaml")

    report = build_network_impairment_report(catalog=catalog, target_class="staging")

    assert report["status"] == "planned"
    assert report["entry_count"] == 4
    assert report["target_details"]["inventory_hosts"] == [
        "docker-runtime-staging-lv3",
        "postgres-staging-lv3",
        "monitoring-staging-lv3",
        "backup-staging-lv3",
    ]


def test_network_impairment_matrix_script_writes_report(tmp_path: Path) -> None:
    from scripts import network_impairment_matrix

    report_path = tmp_path / "matrix.json"
    payload = network_impairment_matrix.main(
        repo_path=str(REPO_ROOT),
        target_class="staging",
        output_format="json",
        report_file=str(report_path),
    )

    assert payload["status"] == "planned"
    assert payload["report_file"] == str(report_path)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["target_class"] == "staging"
