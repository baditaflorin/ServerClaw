from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import parse_lynis_report as parser  # noqa: E402


def test_parse_report_text_extracts_hardening_index_and_findings() -> None:
    report = parser.parse_report_text(
        (
            "hardening_index=72\n"
            "warning[]=AUTH-9208|Set a password hashing iteration count\n"
            "suggestion[]=KRNL-6000|Consider enabling kernel hardening\n"
        ),
        host="docker-runtime-lv3",
        suppressions={},
    )

    assert report["host"] == "docker-runtime-lv3"
    assert report["hardening_index"] == 72
    assert report["finding_counts"]["warning"] == 1
    assert report["finding_counts"]["suggestion"] == 1
    assert report["findings"][0]["id"] == "AUTH-9208"


def test_parse_report_text_hides_suppressed_findings_by_default() -> None:
    report = parser.parse_report_text(
        "warning[]=AUTH-9208|Set a password hashing iteration count\n",
        host="docker-runtime-lv3",
        suppressions={"AUTH-9208": {"reason": "accepted risk"}},
    )

    assert report["findings"] == []
    assert report["finding_counts"]["suppressed"] == 1
    assert report["suppressed_findings"][0]["suppressed"] is True
