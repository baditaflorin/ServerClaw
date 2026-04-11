from __future__ import annotations

import pytest
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import container_image_policy as policy  # noqa: E402


def test_split_image_reference_supports_generic_registry_hosts() -> None:
    assert policy.split_image_reference("artifacts.plane.so/makeplane/plane-backend") == (
        "artifacts.plane.so",
        "makeplane/plane-backend",
    )


def test_fetch_bearer_token_returns_none_for_generic_registry() -> None:
    assert policy.fetch_bearer_token("artifacts.plane.so", "makeplane/plane-backend") is None


def test_validate_exception_metadata_rejects_empty_controls() -> None:
    with pytest.raises(ValueError, match="compensating_controls"):
        policy.validate_exception_metadata(
            {
                "owner": "Platform operations",
                "justification": "Temporary exception while upstream publishes a fixed image.",
                "compensating_controls": [],
                "approved_on": "2026-03-29",
                "expires_on": "2026-04-12",
                "remediation_plan": "Refresh the pinned digest during the next image rotation window.",
            },
            "images.example.exception",
        )


def test_validate_exception_metadata_accepts_reason_and_review_by() -> None:
    policy.validate_exception_metadata(
        {
            "owner": "Platform operations",
            "reason": "Temporary exception while the latest approved upstream digest still reports critical findings.",
            "approved_on": "2026-03-29",
            "review_by": "2026-04-12",
        },
        "images.example.exception",
    )


def test_validate_scan_receipt_accepts_grype_summary_with_backing_receipts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    sbom_receipt = repo_root / "receipts" / "sbom" / "0123456789ab.cdx.json"
    cve_receipt = repo_root / "receipts" / "cve" / "0123456789ab-20260330T120000Z.grype.json"
    sbom_receipt.parent.mkdir(parents=True, exist_ok=True)
    cve_receipt.parent.mkdir(parents=True, exist_ok=True)
    sbom_receipt.write_text("{}\n", encoding="utf-8")
    cve_receipt.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(policy, "repo_path", lambda *parts: repo_root.joinpath(*parts))
    ref = "docker.io/example/runtime:1.0.0@sha256:" + ("0" * 64)
    receipt = {
        "schema_version": "1.0.0",
        "image_id": "example_runtime",
        "image_ref": ref,
        "scanner": "grype",
        "scanned_on": "2026-03-30",
        "sbom_receipt": "receipts/sbom/0123456789ab.cdx.json",
        "cve_receipt": "receipts/cve/0123456789ab-20260330T120000Z.grype.json",
        "summary": {
            "critical": 0,
            "high": 1,
            "blocking_findings_with_fix": 1,
            "total_matches": 3,
        },
    }

    policy.validate_scan_receipt(
        receipt, repo_root / "receipts" / "image-scans" / "example.json", "example_runtime", ref
    )
