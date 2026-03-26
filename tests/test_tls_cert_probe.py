from __future__ import annotations

from datetime import UTC, datetime
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import tls_cert_probe as probe  # noqa: E402


def test_resolve_ca_bundle_path_uses_local_step_ca_root(tmp_path, monkeypatch) -> None:
    root_file = tmp_path / "root_ca.crt"
    root_file.write_text("dummy-root")
    monkeypatch.setattr(probe, "STEP_CA_LOCAL_ROOT_CERTIFICATE_PATH", root_file)
    monkeypatch.setattr(probe, "resolve_shared_repo_path", lambda *parts: None)

    result = probe.resolve_ca_bundle_path({"expected_issuer": "step-ca"})

    assert result == root_file


def test_resolve_ca_bundle_path_skips_missing_step_ca_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        probe,
        "STEP_CA_LOCAL_ROOT_CERTIFICATE_PATH",
        tmp_path / "missing-root_ca.crt",
    )
    monkeypatch.setattr(probe, "resolve_shared_repo_path", lambda *parts: None)

    result = probe.resolve_ca_bundle_path({"expected_issuer": "step-ca"})

    assert result is None


def test_resolve_ca_bundle_path_falls_back_to_shared_repo_root(tmp_path, monkeypatch) -> None:
    shared_root = tmp_path / "shared-root_ca.crt"
    shared_root.write_text("dummy-root")
    monkeypatch.setattr(
        probe,
        "STEP_CA_LOCAL_ROOT_CERTIFICATE_PATH",
        tmp_path / "missing-root_ca.crt",
    )
    monkeypatch.setattr(probe, "resolve_shared_repo_path", lambda *parts: shared_root)

    result = probe.resolve_ca_bundle_path({"expected_issuer": "step-ca"})

    assert result == shared_root


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
        lambda host, port, server_name=None, ca_bundle_path=None, timeout_seconds=5.0: {
            "subject": "commonName=grafana.lv3.org",
            "issuer": "commonName=Let's Encrypt",
            "not_after": datetime(2026, 4, 10, tzinfo=UTC),
        },
    )

    result = probe.evaluate_certificate(certificate, now=datetime(2026, 3, 23, tzinfo=UTC))

    assert result["severity"] == "warning"
    assert result["status"] == "expiring_warning"


def test_evaluate_certificate_uses_hour_policy_for_short_lived_certificates(monkeypatch) -> None:
    certificate = {
        "id": "openbao-proxy",
        "service_id": "openbao",
        "summary": "OpenBao proxy certificate",
        "expected_issuer": "step-ca",
        "endpoint": {"host": "100.64.0.1", "port": 8200, "server_name": "100.64.0.1"},
        "policy": {"warn_hours": 6, "critical_hours": 2},
    }

    monkeypatch.setattr(
        probe,
        "probe_tls_certificate",
        lambda host, port, server_name=None, ca_bundle_path=None, timeout_seconds=5.0: {
            "subject": "commonName=100.64.0.1",
            "issuer": "commonName=LV3 Internal CA Intermediate CA",
            "not_after": datetime(2026, 3, 23, 4, 30, tzinfo=UTC),
        },
    )

    result = probe.evaluate_certificate(certificate, now=datetime(2026, 3, 23, 0, 0, tzinfo=UTC))

    assert result["severity"] == "warning"
    assert result["status"] == "expiring_warning"
    assert result["policy_unit"] == "hours"
    assert result["hours_remaining"] == 4


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
        lambda host, port, server_name=None, ca_bundle_path=None, timeout_seconds=5.0: {
            "subject": "commonName=openbao",
            "issuer": "commonName=Let's Encrypt",
            "not_after": datetime(2026, 5, 1, tzinfo=UTC),
        },
    )

    result = probe.evaluate_certificate(certificate, now=datetime(2026, 3, 23, tzinfo=UTC))

    assert result["severity"] == "warning"
    assert result["status"] == "issuer_mismatch"
    assert result["expected_issuer"] == "step-ca"
