from __future__ import annotations

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import https_tls_assurance_targets as targets  # noqa: E402


def test_discover_targets_covers_public_operator_and_internal_https_surfaces() -> None:
    discovered = targets.discover_https_tls_targets()
    by_id = {item["id"]: item for item in discovered}

    assert "api-gateway-public" in by_id
    assert "vaultwarden-operator" in by_id
    assert "openbao-internal" in by_id
    assert "proxmox-ui-public" in by_id
    assert "proxmox-ui-internal" in by_id


def test_internal_ip_targets_use_hostname_override_when_certificate_server_name_differs() -> None:
    discovered = {item["id"]: item for item in targets.discover_https_tls_targets()}
    proxmox_internal = discovered["proxmox-ui-internal"]

    assert proxmox_internal["probe_url"] == "https://100.64.0.1:8006/api2/json/version"
    assert proxmox_internal["probe_hostname"] == "proxmox.example.org"
    assert proxmox_internal["testssl_url"] == "https://proxmox.example.org:8006/"
    assert proxmox_internal["testssl_ip"] == "100.64.0.1"


def test_public_targets_prefer_uptime_kuma_monitor_url_when_present() -> None:
    discovered = {item["id"]: item for item in targets.discover_https_tls_targets()}
    matrix_public = discovered["matrix-synapse-public"]

    assert matrix_public["probe_url"] == "https://10.10.10.10:443/_matrix/client/versions"
    assert matrix_public["probe_hostname"] == "matrix.example.com"
    assert matrix_public["display_url"] == "https://matrix.example.com:443/_matrix/client/versions"


def test_public_targets_probe_through_internal_edge_with_hostname_override() -> None:
    discovered = {item["id"]: item for item in targets.discover_https_tls_targets()}
    proxmox_public = discovered["proxmox-ui-public"]

    assert proxmox_public["probe_url"] == "https://10.10.10.10:443/"
    assert proxmox_public["probe_hostname"] == "proxmox.example.com"
    assert proxmox_public["display_url"] == "https://proxmox.example.com:443/"


def test_generated_alert_rules_include_day_and_hour_expiry_windows() -> None:
    discovered = targets.discover_https_tls_targets()
    payload = targets.build_prometheus_alert_rules(discovered)
    alerts = {rule["alert"]: rule for rule in payload["groups"][0]["rules"]}

    assert alerts["TLSCertificateExpiringWarning_api_gateway_public"]["expr"].endswith(" < 21")
    assert alerts["TLSCertificateExpiringCritical_openbao_internal"]["expr"].endswith(" < 2")


def test_workflow_implementation_refs_distinguish_sources_from_generated_outputs() -> None:
    catalog = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))
    workflow = catalog["workflows"]["weekly-https-tls-assurance"]
    implementation_refs = set(workflow["implementation_refs"])

    assert "scripts/generate_https_tls_assurance.py" in implementation_refs
    assert "scripts/https_tls_assurance.py" in implementation_refs
    assert "config/prometheus/file_sd/https_tls_targets.yml" not in implementation_refs
    assert "config/prometheus/rules/https_tls_alerts.yml" not in implementation_refs
    assert "receipts/https-tls-assurance" not in implementation_refs
