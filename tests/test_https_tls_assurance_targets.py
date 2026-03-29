from __future__ import annotations

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
    assert proxmox_internal["probe_hostname"] == "proxmox.lv3.org"
    assert proxmox_internal["testssl_url"] == "https://proxmox.lv3.org:8006/"
    assert proxmox_internal["testssl_ip"] == "100.64.0.1"


def test_public_targets_prefer_uptime_kuma_monitor_url_when_present() -> None:
    discovered = {item["id"]: item for item in targets.discover_https_tls_targets()}
    matrix_public = discovered["matrix-synapse-public"]

    assert matrix_public["probe_url"] == "https://matrix.lv3.org:443/_matrix/client/versions"
    assert matrix_public["display_url"] == "https://matrix.lv3.org:443/_matrix/client/versions"


def test_generated_alert_rules_include_day_and_hour_expiry_windows() -> None:
    discovered = targets.discover_https_tls_targets()
    payload = targets.build_prometheus_alert_rules(discovered)
    alerts = {rule["alert"]: rule for rule in payload["groups"][0]["rules"]}

    assert alerts["TLSCertificateExpiringWarning_api_gateway_public"]["expr"].endswith(" < 21")
    assert alerts["TLSCertificateExpiringCritical_openbao_internal"]["expr"].endswith(" < 2")
