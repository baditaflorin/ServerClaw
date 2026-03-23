from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import security_posture_report as report  # noqa: E402


def test_build_report_detects_new_lynis_findings_and_hardening_delta() -> None:
    previous = json.loads((REPO_ROOT / "tests" / "fixtures" / "security_posture_previous.json").read_text())
    host_reports = [
        {
            "host": "docker-runtime-lv3",
            "hardening_index": 72,
            "finding_counts": {"warning": 2, "suggestion": 1, "suppressed": 0},
            "findings": [
                {
                    "id": "AUTH-9208",
                    "type": "warning",
                    "description": "Set a password hashing iteration count",
                    "suggestion": "",
                    "raw": "AUTH-9208|Set a password hashing iteration count",
                    "suppressed": False,
                },
                {
                    "id": "PKGS-7392",
                    "type": "warning",
                    "description": "Apply the latest Debian security updates",
                    "suggestion": "",
                    "raw": "PKGS-7392|Apply the latest Debian security updates",
                    "suppressed": False,
                },
            ],
            "suppressed_findings": [],
        }
    ]
    trivy_payloads = {
        "docker-runtime-lv3": [
            {
                "image": "ghcr.io/example/app:1.0.0",
                "artifact_name": "ghcr.io/example/app:1.0.0",
                "severity_counts": {"HIGH": 2, "CRITICAL": 1},
                "vulnerabilities": [
                    {
                        "cve_id": "CVE-2026-0001",
                        "severity": "CRITICAL",
                        "package": "openssl",
                        "installed": "3.0.0",
                        "fixed_in": "3.0.1",
                        "title": "critical issue",
                    }
                ],
            }
        ]
    }

    built = report.build_report(
        environment="production",
        host_reports=host_reports,
        trivy_payloads=trivy_payloads,
        previous_report=previous,
    )

    assert built["hosts"][0]["new_findings_since_last_scan"] == 1
    assert built["hosts"][0]["hardening_index_delta"] == -2
    assert built["summary"]["total_critical_cves"] == 1
    assert built["summary"]["total_high_cves"] == 2
    assert built["summary"]["status"] == "critical"


def test_build_security_events_emits_summary_and_critical_findings() -> None:
    events = report.build_security_events(
        {
            "environment": "production",
            "generated_at": "2026-03-23T21:00:00Z",
            "summary": {
                "status": "critical",
                "status_code": 2,
                "total_critical_cves": 1,
                "total_high_cves": 2,
                "lowest_hardening_index": 72,
                "new_lynis_findings": 1,
            },
            "hosts": [
                {
                    "host": "docker-runtime-lv3",
                    "hardening_index": 72,
                    "hardening_index_delta": -11,
                }
            ],
            "images": [
                {
                    "host": "docker-runtime-lv3",
                    "image": "ghcr.io/example/app:1.0.0",
                    "cves": [
                        {
                            "cve_id": "CVE-2026-0001",
                            "severity": "CRITICAL",
                        }
                    ],
                }
            ],
        }
    )

    assert events[0]["event"] == "platform.security.report"
    critical_events = [item for item in events if item["event"] == "platform.security.critical-finding"]
    assert len(critical_events) == 2
