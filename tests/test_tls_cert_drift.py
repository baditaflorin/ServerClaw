from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tls_cert_drift as drift  # noqa: E402


def test_collect_drift_marks_expiring_certificate_critical(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "collect_certificate_results",
        lambda timeout_seconds=5.0, now=None: [
            {
                "certificate_id": "grafana-edge",
                "service_id": "grafana",
                "severity": "critical",
                "status": "expiring_critical",
                "days_remaining": 5,
                "issuer": "commonName=Let's Encrypt",
                "not_after": "2026-03-28T00:00:00Z",
            }
        ],
    )

    records = drift.collect_drift()

    assert len(records) == 1
    assert records[0]["severity"] == "critical"
    assert records[0]["resource"] == "grafana-edge"


def test_collect_drift_warns_on_issuer_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "collect_certificate_results",
        lambda timeout_seconds=5.0, now=None: [
            {
                "certificate_id": "proxmox-ui",
                "service_id": "proxmox_ui",
                "severity": "warning",
                "status": "issuer_mismatch",
                "issuer": "commonName=step-ca",
                "expected_issuer": "letsencrypt",
                "not_after": "2026-05-02T00:00:00Z",
            }
        ],
    )

    records = drift.collect_drift()

    assert len(records) == 1
    assert records[0]["severity"] == "warn"
    assert records[0]["expected_provider"] == "letsencrypt"


def test_collect_drift_uses_hour_based_detail_for_short_lived_certificates(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "collect_certificate_results",
        lambda timeout_seconds=5.0, now=None: [
            {
                "certificate_id": "openbao-proxy",
                "service_id": "openbao",
                "severity": "warning",
                "status": "expiring_warning",
                "hours_remaining": 4,
                "policy_unit": "hours",
                "issuer": "commonName=LV3 Internal CA",
                "not_after": "2026-03-23T04:30:00Z",
            }
        ],
    )

    records = drift.collect_drift()

    assert len(records) == 1
    assert records[0]["severity"] == "warn"
    assert records[0]["detail"] == "certificate expires in 4 hours"
