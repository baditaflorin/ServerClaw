from pathlib import Path

import pytest

import live_apply_receipts


def build_receipt(source_commit: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "receipt_id": "2026-03-23-test-receipt",
        "environment": "production",
        "applied_on": "2026-03-23",
        "recorded_on": "2026-03-23",
        "recorded_by": "codex",
        "source_commit": source_commit,
        "repo_version_context": "0.80.0",
        "workflow_id": "test-workflow",
        "adr": "0083",
        "summary": "Test receipt.",
        "targets": [{"kind": "guest", "name": "docker-build-lv3"}],
        "verification": [{"check": "Smoke", "result": "pass", "observed": "Healthy."}],
        "evidence_refs": ["docs/adr/0083-docker-based-check-runner.md"],
        "notes": [],
    }


def test_validate_receipt_accepts_commit_hash_without_git_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    live_apply_receipts.validate_receipt(
        build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99"),
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_rejects_non_hash_without_git_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    with pytest.raises(ValueError, match="must look like a git commit hash"):
        live_apply_receipts.validate_receipt(
            build_receipt("not-a-commit"),
            Path("2026-03-23-test-receipt.json"),
            {"workflows": {"test-workflow": {}}},
        )


def test_validate_receipt_accepts_hash_when_git_metadata_lacks_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_lookup_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    live_apply_receipts.validate_receipt(
        build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99"),
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_rejects_non_hash_when_git_metadata_lacks_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_lookup_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    with pytest.raises(ValueError, match="must look like a git commit hash"):
        live_apply_receipts.validate_receipt(
            build_receipt("not-a-commit"),
            Path("2026-03-23-test-receipt.json"),
            {"workflows": {"test-workflow": {}}},
        )


def test_validate_receipt_accepts_legacy_live_apply_workflow_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["receipt_id"] = "2026-03-23-adr-0077-compose-runtime-secrets-live-apply"
    receipt["workflow_id"] = "adr-0077-compose-runtime-secrets-live-apply"

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-adr-0077-compose-runtime-secrets-live-apply.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_receipt_id_with_session_appends_normalized_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LV3_SESSION_RECEIPT_SUFFIX", "ADR 0156 / Test")

    receipt_id = live_apply_receipts.receipt_id_with_session("2026-03-25-adr-0156-live-apply")

    assert receipt_id == "2026-03-25-adr-0156-live-apply-adr-0156-test"


def test_validate_receipt_accepts_optional_correction_loop_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["correction_loop"] = {
        "loop_id": "runtime_self_correction_watchers",
        "surface": "platform-observation-loop",
        "diagnosis": "contract_drift",
        "repair_action": "reconcile",
        "verification": "durable loop run resolved",
    }

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_receipt_environment_for_path_accepts_catalog_driven_subdirectories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        live_apply_receipts,
        "receipt_subdirectory_environments",
        lambda: {"staging", "development", "preview"},
    )

    assert (
        live_apply_receipts.receipt_environment_for_path(
            live_apply_receipts.RECEIPTS_DIR / "development" / "2026-03-27-test.json"
        )
        == "development"
    )
    assert (
        live_apply_receipts.receipt_environment_for_path(
            live_apply_receipts.RECEIPTS_DIR / "2026-03-27-test.json"
        )
        == "production"
    )
    assert (
        live_apply_receipts.receipt_environment_for_path(
            live_apply_receipts.RECEIPTS_DIR / "preview" / "2026-03-27-test.json"
        )
        == "preview"
    )
