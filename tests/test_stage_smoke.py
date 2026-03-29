from __future__ import annotations

from scripts.stage_smoke import (
    declared_smoke_suites,
    latest_matching_smoke_receipt,
    matched_smoke_suite_ids,
)


def test_declared_smoke_suites_fall_back_to_default_for_active_environment() -> None:
    service = {
        "id": "grafana",
        "name": "Grafana",
        "environments": {
            "production": {"status": "active", "url": "https://grafana.lv3.org"},
        },
    }

    suites = declared_smoke_suites(service, "production")

    assert len(suites) == 1
    assert suites[0]["id"] == "default-primary-smoke"
    assert suites[0]["required_verification_checks"] == ["smoke"]


def test_declared_smoke_suites_preserve_explicit_override() -> None:
    service = {
        "id": "ops_portal",
        "name": "Ops Portal",
        "environments": {
            "production": {
                "status": "active",
                "url": "https://ops.lv3.org",
                "smoke_suites": [
                    {
                        "id": "portal-overview",
                        "name": "Portal overview",
                        "description": "Verify the overview partial renders.",
                        "required_verification_checks": ["runtime assurance"],
                    }
                ],
            }
        },
    }

    suites = declared_smoke_suites(service, "production")

    assert [suite["id"] for suite in suites] == ["portal-overview"]


def test_latest_matching_smoke_receipt_uses_declared_verification_tokens() -> None:
    suites = [
        {
            "id": "portal-overview",
            "name": "Portal overview",
            "description": "Verify the overview partial renders.",
            "required_verification_checks": ["runtime assurance", "smoke"],
        }
    ]
    receipts = [
        {
            "receipt_id": "older",
            "recorded_at": "2026-03-29T09:00:00Z",
            "verification": [{"check": "Smoke", "result": "pass", "observed": "Generic smoke only."}],
        },
        {
            "receipt_id": "newer",
            "recorded_at": "2026-03-29T10:00:00Z",
            "verification": [
                {"check": "Runtime assurance smoke", "result": "pass", "observed": "Overview rendered."}
            ],
        },
    ]

    matched_receipt, matched_ids = latest_matching_smoke_receipt(receipts, suites)

    assert matched_receipt is not None
    assert matched_receipt["receipt_id"] == "newer"
    assert matched_ids == ["portal-overview"]


def test_matched_smoke_suite_ids_returns_empty_when_smoke_token_missing() -> None:
    receipt = {
        "verification": [{"check": "Grafana health", "result": "pass", "observed": "Ready."}],
    }
    suites = [
        {
            "id": "default-primary-smoke",
            "name": "Default primary smoke",
            "description": "Require a smoke token.",
            "required_verification_checks": ["smoke"],
        }
    ]

    assert matched_smoke_suite_ids(receipt, suites) == []
