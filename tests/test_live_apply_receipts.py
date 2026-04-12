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
        "targets": [{"kind": "guest", "name": "docker-build"}],
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


def test_validate_receipt_accepts_hash_when_git_metadata_has_no_matching_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_lookup_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_exists", lambda _commit: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")
    monkeypatch.delenv("LV3_REQUIRE_RECEIPT_SOURCE_COMMIT_OBJECTS", raising=False)

    live_apply_receipts.validate_receipt(
        build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99"),
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_rejects_missing_object_in_strict_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_lookup_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_exists", lambda _commit: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")
    monkeypatch.setenv("LV3_REQUIRE_RECEIPT_SOURCE_COMMIT_OBJECTS", "1")

    with pytest.raises(ValueError, match="current git object database"):
        live_apply_receipts.validate_receipt(
            build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99"),
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


def test_validate_receipt_accepts_workstream_live_apply_workflow_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["receipt_id"] = "2026-04-12-ws-0381-branch-live-apply"
    receipt["workflow_id"] = "ws-0381-branch-live-apply"

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-04-12-ws-0381-branch-live-apply.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_accepts_retired_workflow_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["workflow_id"] = "converge-open-webui"

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_accepts_historical_receipt_without_adr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt.pop("adr")

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_accepts_historical_evidence_ref_from_source_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_lookup_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_exists", lambda _commit: True)
    monkeypatch.setattr(
        live_apply_receipts,
        "git_path_exists_in_commit",
        lambda _commit, ref: ref == "docs/adr/historical-evidence.md",
    )
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["evidence_refs"] = ["docs/adr/historical-evidence.md"]

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_accepts_historical_evidence_ref_from_git_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_lookup_available", lambda: True)
    monkeypatch.setattr(live_apply_receipts, "git_commit_exists", lambda _commit: True)
    monkeypatch.setattr(live_apply_receipts, "git_path_exists_in_commit", lambda _commit, _ref: False)
    monkeypatch.setattr(
        live_apply_receipts,
        "git_path_exists_in_history",
        lambda ref: ref == "docs/adr/historical-evidence.md",
    )
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["evidence_refs"] = ["docs/adr/historical-evidence.md"]

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-test-receipt.json"),
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


def test_validate_receipt_accepts_optional_smoke_suites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["smoke_suites"] = [
        {
            "suite_id": "production-windmill-primary-path",
            "service_id": "windmill",
            "environment": "production",
            "status": "passed",
            "executed_at": "2026-03-23T12:00:00Z",
            "summary": "1 passed, 0 failed, 0 skipped",
            "report_ref": "docs/adr/0083-docker-based-check-runner.md",
        }
    ]

    live_apply_receipts.validate_receipt(
        receipt,
        Path("2026-03-23-test-receipt.json"),
        {"workflows": {"test-workflow": {}}},
    )


def test_validate_receipt_accepts_shared_root_receipt_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    shared_root = tmp_path / "repo"
    worktree_root = shared_root / ".worktrees" / "ws-0380"
    shared_receipts = shared_root / "receipts" / "live-applies"
    worktree_receipts = worktree_root / "receipts" / "live-applies"
    shared_receipts.mkdir(parents=True, exist_ok=True)
    worktree_receipts.mkdir(parents=True, exist_ok=True)
    (shared_receipts / "2026-03-23-shared-receipt.json").write_text("{}", encoding="utf-8")
    (shared_receipts / "evidence").mkdir(parents=True, exist_ok=True)
    (shared_receipts / "evidence" / "2026-03-23-shared-report.txt").write_text("ok\n", encoding="utf-8")

    monkeypatch.setattr(live_apply_receipts, "REPO_ROOT", worktree_root)
    monkeypatch.setattr(live_apply_receipts, "RECEIPTS_DIR", worktree_receipts)
    monkeypatch.setattr(live_apply_receipts, "shared_repo_root", lambda _root=None: shared_root)
    monkeypatch.setattr(
        live_apply_receipts,
        "repo_path",
        lambda *parts: shared_root.joinpath(*parts) if parts and parts[0] == "receipts" else worktree_root.joinpath(*parts),
    )
    monkeypatch.setattr(live_apply_receipts, "git_metadata_available", lambda: False)
    monkeypatch.setattr(live_apply_receipts, "receipt_environment_for_path", lambda _path: "production")

    receipt = build_receipt("c4db21b414c44e5bcd9d6c1fe5ae4fdd9e5cac99")
    receipt["evidence_refs"] = ["receipts/live-applies/2026-03-23-shared-receipt.json"]
    receipt["smoke_suites"] = [
        {
            "suite_id": "production-shared-report",
            "service_id": "windmill",
            "environment": "production",
            "status": "passed",
            "executed_at": "2026-03-23T12:00:00Z",
            "summary": "1 passed, 0 failed, 0 skipped",
            "report_ref": "receipts/live-applies/evidence/2026-03-23-shared-report.txt",
        }
    ]

    live_apply_receipts.validate_receipt(
        receipt,
        worktree_receipts / "2026-03-23-test-receipt.json",
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
        live_apply_receipts.receipt_environment_for_path(live_apply_receipts.RECEIPTS_DIR / "2026-03-27-test.json")
        == "production"
    )
    assert (
        live_apply_receipts.receipt_environment_for_path(
            live_apply_receipts.RECEIPTS_DIR / "preview" / "2026-03-27-test.json"
        )
        == "preview"
    )


def test_iter_receipt_paths_skips_nested_evidence_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    receipts_dir = tmp_path / "receipts" / "live-applies"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    tracked_receipt = receipts_dir / "2026-03-29-adr-0251-stage-smoke-live-apply.json"
    tracked_receipt.write_text("{}", encoding="utf-8")
    evidence_json = receipts_dir / "preview" / "evidence" / "2026-03-29-adr-0251-gate-status-live.json"
    evidence_json.parent.mkdir(parents=True, exist_ok=True)
    evidence_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(live_apply_receipts, "RECEIPTS_DIR", receipts_dir)
    monkeypatch.setattr(live_apply_receipts, "shared_repo_root", lambda _root=None: tmp_path)

    assert live_apply_receipts.iter_receipt_paths(receipts_dir) == [tracked_receipt]


def test_iter_receipt_paths_skips_evidence_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "2026-03-29-valid-live-apply.json").write_text("{}", encoding="utf-8")
    (tmp_path / "staging").mkdir()
    (tmp_path / "staging" / "2026-03-29-valid-staging-live-apply.json").write_text("{}", encoding="utf-8")
    (tmp_path / "preview").mkdir()
    (tmp_path / "preview" / "2026-03-29-valid-preview-live-apply.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "2026-03-29-non-receipt-evidence.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(live_apply_receipts, "RECEIPTS_DIR", tmp_path)
    monkeypatch.setattr(live_apply_receipts, "shared_repo_root", lambda _root=None: tmp_path)

    paths = [path.relative_to(tmp_path).as_posix() for path in live_apply_receipts.iter_receipt_paths(tmp_path)]

    assert paths == [
        "2026-03-29-valid-live-apply.json",
        "preview/2026-03-29-valid-preview-live-apply.json",
        "staging/2026-03-29-valid-staging-live-apply.json",
    ]
