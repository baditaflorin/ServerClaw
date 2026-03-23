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
