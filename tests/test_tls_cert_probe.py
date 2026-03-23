from __future__ import annotations

from datetime import UTC, datetime
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tls_cert_probe as probe  # noqa: E402


def test_evaluate_certificate_warns_on_expiry(monkeypatch) -> None:
    certificate = {
        "id": "grafana-edge",
        "service_id": "grafana",
        "summary": "Grafana public certificate",
        "expected_issuer": "letsencrypt",
        "endpoint": {"host": "grafana.lv3.org", "port": 443, "server_name": "grafana.lv3.org"},
        "policy": {"warn_days": 21, "critical_days": 14},
    }

    monkeypatch.setattr(
        probe,
        "probe_tls_certificate",
        lambda host, port, server_name=None, timeout_seconds=5.0: {
            "subject": "commonName=grafana.lv3.org",
            "issuer": "commonName=Let's Encrypt",
            "not_after": datetime(2026, 4, 10, tzinfo=UTC),
        },
    )

    result = probe.evaluate_certificate(certificate, now=datetime(2026, 3, 23, tzinfo=UTC))

    assert result["severity"] == "warning"
    assert result["status"] == "expiring_warning"


def test_evaluate_certificate_warns_on_issuer_mismatch(monkeypatch) -> None:
    certificate = {
        "id": "openbao-proxy",
        "service_id": "openbao",
        "summary": "OpenBao proxy certificate",
        "expected_issuer": "step-ca",
        "endpoint": {"host": "100.118.189.95", "port": 8200, "server_name": "100.118.189.95"},
        "policy": {"warn_days": 21, "critical_days": 14},
    }

    monkeypatch.setattr(
        probe,
        "probe_tls_certificate",
        lambda host, port, server_name=None, timeout_seconds=5.0: {
            "subject": "commonName=openbao",
            "issuer": "commonName=Let's Encrypt",
            "not_after": datetime(2026, 5, 1, tzinfo=UTC),
        },
    )

    result = probe.evaluate_certificate(certificate, now=datetime(2026, 3, 23, tzinfo=UTC))

    assert result["severity"] == "warning"
    assert result["status"] == "issuer_mismatch"
    assert result["expected_issuer"] == "step-ca"
