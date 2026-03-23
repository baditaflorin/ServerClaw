from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import dns_drift as drift  # noqa: E402


def test_collect_drift_reports_wrong_record(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "load_json",
        lambda path: {
            "subdomains": [
                {
                    "fqdn": "grafana.lv3.org",
                    "service_id": "grafana",
                    "status": "active",
                    "target": "65.108.75.123",
                    "owner_adr": "0011",
                }
            ]
        },
    )
    monkeypatch.setattr(drift, "query_records", lambda name, record_type, dns_server=None: ["203.0.113.9"])

    records = drift.collect_drift()

    assert len(records) == 1
    assert records[0]["record_type"] == "A"
    assert "65.108.75.123" in records[0]["detail"]


def test_collect_drift_skips_matching_record(monkeypatch) -> None:
    monkeypatch.setattr(
        drift,
        "load_json",
        lambda path: {
            "subdomains": [
                {
                    "fqdn": "ops.lv3.org",
                    "service_id": "ops_portal",
                    "status": "active",
                    "target": "65.108.75.123",
                    "owner_adr": "0074",
                }
            ]
        },
    )
    monkeypatch.setattr(drift, "query_records", lambda name, record_type, dns_server=None: ["65.108.75.123"])

    assert drift.collect_drift() == []
