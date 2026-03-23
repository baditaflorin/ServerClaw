from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tls_cert_drift as drift  # noqa: E402


def test_collect_drift_marks_expiring_certificate_critical(monkeypatch) -> None:
    service_payload = {
        "services": [
            {
                "id": "grafana",
                "public_url": "https://grafana.lv3.org",
            }
        ]
    }
    subdomain_payload = {
        "subdomains": [
            {
                "fqdn": "grafana.lv3.org",
                "tls": {"provider": "letsencrypt"},
            }
        ]
    }

    def fake_load_json(path):
        if path == drift.SERVICE_CATALOG_PATH:
            return service_payload
        return subdomain_payload

    monkeypatch.setattr(drift, "load_json", fake_load_json)
    monkeypatch.setattr(
        drift,
        "probe_tls_certificate",
        lambda host, port, server_name=None, timeout_seconds=5: (
            "commonName=Let's Encrypt",
            int(drift.utc_now().timestamp() + 5 * 24 * 60 * 60),
        ),
    )

    records = drift.collect_drift()

    assert len(records) == 1
    assert records[0]["severity"] == "critical"


def test_collect_drift_warns_on_issuer_mismatch(monkeypatch) -> None:
    service_payload = {
        "services": [
            {
                "id": "proxmox_ui",
                "public_url": "https://proxmox.lv3.org",
            }
        ]
    }
    subdomain_payload = {
        "subdomains": [
            {
                "fqdn": "proxmox.lv3.org",
                "tls": {"provider": "letsencrypt"},
            }
        ]
    }

    def fake_load_json(path):
        if path == drift.SERVICE_CATALOG_PATH:
            return service_payload
        return subdomain_payload

    monkeypatch.setattr(drift, "load_json", fake_load_json)
    monkeypatch.setattr(
        drift,
        "probe_tls_certificate",
        lambda host, port, server_name=None, timeout_seconds=5: (
            "commonName=step-ca",
            int(drift.utc_now().timestamp() + 40 * 24 * 60 * 60),
        ),
    )

    records = drift.collect_drift()

    assert len(records) == 1
    assert records[0]["severity"] == "warn"
    assert records[0]["expected_provider"] == "letsencrypt"
