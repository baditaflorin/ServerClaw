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
