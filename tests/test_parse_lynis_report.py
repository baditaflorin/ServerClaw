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
        host="docker-runtime",
        suppressions={},
    )

    assert report["host"] == "docker-runtime"
    assert report["hardening_index"] == 72
    assert report["finding_counts"]["warning"] == 1
    assert report["finding_counts"]["suggestion"] == 1
    assert report["findings"][0]["id"] == "AUTH-9208"


def test_parse_report_text_hides_suppressed_findings_by_default() -> None:
    report = parser.parse_report_text(
        "warning[]=AUTH-9208|Set a password hashing iteration count\n",
        host="docker-runtime",
        suppressions={"AUTH-9208": {"reason": "accepted risk"}},
    )

    assert report["findings"] == []
    assert report["finding_counts"]["suppressed"] == 1
    assert report["suppressed_findings"][0]["suppressed"] is True


def test_host_scoped_suppression_does_not_hide_same_finding_on_other_hosts() -> None:
    suppressions = {
        "FIRE-4512": {
            "hosts": ["nginx"],
            "reason": "The host uses nftables.",
        }
    }

    edge_report = parser.parse_report_text(
        "warning[]=FIRE-4512|iptables module(s) loaded, but no rules active\n",
        host="nginx",
        suppressions=suppressions,
    )
    other_report = parser.parse_report_text(
        "warning[]=FIRE-4512|iptables module(s) loaded, but no rules active\n",
        host="docker-runtime",
        suppressions=suppressions,
    )

    assert edge_report["findings"] == []
    assert edge_report["finding_counts"]["suppressed"] == 1
    assert other_report["finding_counts"]["warning"] == 1
    assert other_report["findings"][0]["suppressed"] is False


def test_live_platform_suppressions_are_limited_to_verified_hosts() -> None:
    suppressions = parser.load_suppressions()

    for finding_id in ("PKGS-7388", "FIRE-4512"):
        expected_hosts = ["nginx", "coolify", "runtime-control"] if finding_id == "PKGS-7388" else ["nginx", "coolify"]
        assert suppressions[finding_id]["hosts"] == expected_hosts

    for host in ("nginx", "coolify", "runtime-control"):
        report = parser.parse_report_text(
            "warning[]=PKGS-7388|Can't find any security repository\n"
            "warning[]=FIRE-4512|iptables module(s) loaded, but no rules active\n",
            host=host,
            suppressions=suppressions,
        )
        expected_suppressed = 2 if host in {"nginx", "coolify"} else 1
        assert report["finding_counts"]["warning"] == 2 - expected_suppressed
        assert report["finding_counts"]["suppressed"] == expected_suppressed

    other_host = parser.parse_report_text(
        "warning[]=PKGS-7388|Can't find any security repository\n"
        "warning[]=FIRE-4512|iptables module(s) loaded, but no rules active\n",
        host="docker-runtime",
        suppressions=suppressions,
    )
    assert other_host["finding_counts"]["warning"] == 2
    assert other_host["finding_counts"]["suppressed"] == 0
