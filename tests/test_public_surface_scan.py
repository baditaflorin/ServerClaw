from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import public_surface_scan as scan  # noqa: E402


def test_repo_policy_loads() -> None:
    policy = scan.load_public_surface_scan_policy()

    assert policy["schema_version"] == "1.0.0"
    assert policy["nuclei"]["target"] == "https://example.com"


def test_public_surface_scan_cli_help_runs() -> None:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "public_surface_scan.py"), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "public-surface security scan" in completed.stdout


def test_discover_scan_targets_only_includes_active_public_https_targets() -> None:
    targets = scan.discover_scan_targets("production")
    target_map = {item["fqdn"]: item for item in targets}

    assert "grafana.example.com" in target_map
    assert "database.example.com" not in target_map
    assert target_map["ops.example.com"]["requires_auth"] is True


def test_header_and_version_findings_detect_missing_controls() -> None:
    policy = scan.load_public_surface_scan_policy()
    target = {
        "fqdn": "grafana.example.com",
        "requires_auth": False,
    }
    response = {
        "status": 200,
        "headers": {
            "Server": "grafana/11.0.0",
            "X-Content-Type-Options": "nosniff",
        },
        "body": "",
    }

    findings = scan.evaluate_header_findings(
        scan_id="scan-1",
        target=target,
        response=response,
        policy=policy,
    )
    findings.extend(
        scan.evaluate_version_disclosure_findings(
            scan_id="scan-1",
            target=target,
            response=response,
            policy=policy,
        )
    )

    finding_ids = {item["finding_id"] for item in findings}
    assert "headers.strict_transport_security" in finding_ids
    assert "version.server" in finding_ids


def test_auth_findings_require_redirect_and_hide_sensitive_content() -> None:
    policy = scan.load_public_surface_scan_policy()
    target = {
        "fqdn": "ops.example.com",
        "requires_auth": True,
    }
    response = {
        "status": 200,
        "headers": {
            "X-Auth-Request-User": "ops@example.com",
        },
        "body": "<html>Ops Portal dashboard</html>",
    }

    findings = scan.evaluate_auth_findings(
        scan_id="scan-1",
        target=target,
        response=response,
        policy=policy,
    )

    finding_ids = {item["finding_id"] for item in findings}
    assert "auth.redirect" in finding_ids
    assert "auth.header.X-Auth-Request-User".replace("X-", "x-") not in finding_ids
    assert any(item["finding_id"].startswith("auth.header.") for item in findings)
    assert any(item["finding_id"].startswith("auth.body.") for item in findings)


def test_classify_testssl_and_nuclei_findings() -> None:
    target = {"fqdn": "grafana.example.com"}
    testssl_findings = scan.classify_testssl_findings(
        scan_id="scan-1",
        target=target,
        raw_findings=[
            {"id": "TLS1", "finding": "TLS 1 offered"},
            {"id": "cert_expirationStatus", "finding": "Certificate expired"},
        ],
    )
    nuclei_findings = scan.classify_nuclei_findings(
        scan_id="scan-1",
        raw_findings=[
            {
                "template-id": "open-redirect",
                "host": "https://example.com",
                "info": {"name": "Open Redirect", "severity": "high"},
            }
        ],
    )

    assert [item["severity"] for item in testssl_findings] == ["high", "critical"]
    assert nuclei_findings[0]["component"] == "open-redirect"


def test_build_report_and_events_summarize_high_and_critical_findings() -> None:
    report = scan.build_report(
        scan_id="20260324T000000Z",
        environment="production",
        targets=[
            {
                "fqdn": "grafana.example.com",
                "service_id": "grafana",
                "exposure": "edge-published",
                "requires_auth": False,
            }
        ],
        http_observations={
            "grafana.example.com": {"status": 200, "final_url": "https://grafana.example.com", "headers": {}}
        },
        tls_results={},
        nuclei_result={
            "artifact": "",
            "returncode": 0,
            "duration_seconds": 0,
            "raw_findings": 0,
            "target": "https://example.com",
        },
        findings=[
            scan.build_finding(
                scan_id="20260324T000000Z",
                severity="high",
                component="tls",
                target="grafana.example.com",
                finding_id="tls.TLS1",
                summary="Deprecated TLS protocol is still accepted.",
                observed="TLS 1 offered",
            ),
            scan.build_finding(
                scan_id="20260324T000000Z",
                severity="critical",
                component="open-redirect",
                target="https://example.com",
                finding_id="open-redirect.sample",
                summary="Open Redirect",
                observed="matcher",
            ),
        ],
        started_at=0.0,
        artifacts_dir=REPO_ROOT / ".local" / "public-surface-scan" / "20260324T000000Z",
    )
    events = scan.build_security_events(report, "receipts/security-scan/20260324T000000Z.json")

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["finding_counts"]["high"] == 1
    assert report["summary"]["finding_counts"]["critical"] == 1
    assert events[0]["event"] == "platform.security.report"
    assert {item["event"] for item in events[1:]} == {
        "platform.security.high-finding",
        "platform.security.critical-finding",
    }
