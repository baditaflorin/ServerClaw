from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.workstream_reconciliation import build_report, render_markdown
from scripts.workstream_reconciliation import validate_new_workstream_metadata


def test_report_flags_mismatches_without_changing_status() -> None:
    report = build_report(
        [
            {
                "id": "ws-one",
                "status": "in_progress",
                "branch": "codex/shared",
                "ready_to_merge": True,
                "live_applied": False,
                "tasks": [{"status": "completed"}],
            },
            {
                "id": "ws-two",
                "status": "in_progress",
                "branch": "codex/shared",
                "ready_to_merge": False,
                "live_applied": True,
                "repositories": ["example/project"],
                "pull_requests": [],
                "tasks": [{"status": "in_progress"}],
            },
            {
                "id": "ws-three",
                "status": "in_progress",
                "canonical_truth": {
                    "included_in_repo_version": "0.180.0",
                    "release_bump": "patch",
                    "changelog_entry": "Already released",
                },
            },
        ]
    )

    assert report["mode"] == "read_only"
    assert report["status_changes_made"] == 0
    assert report["summary"]["workstreams_in_progress"] == 3
    assert report["summary"]["in_progress_with_completion_or_release_signals"] == 3
    first, second, third = report["entries"]
    assert first["status"] == "in_progress"
    assert "status_in_progress_but_ready_to_merge" in first["review_reasons"]
    assert "all_tasks_marked_completed" in first["review_reasons"]
    assert "missing_exact_repository_reference" in first["review_reasons"]
    assert "branch_name_reused" in first["review_reasons"]
    assert "status_in_progress_but_live_applied_flag" in second["review_reasons"]
    assert "no_pull_request_reference" in second["review_reasons"]
    assert second["status"] == "in_progress"
    assert "in_progress_but_included_in_repo_release" in third["review_reasons"]
    assert third["release_bookkeeping"]["included_in_repo_version"] == "0.180.0"


def test_markdown_report_explains_manual_evidence_review() -> None:
    report = build_report([{"id": "ws-one", "status": "in_progress", "ready_to_merge": True, "live_applied": False}])

    markdown = render_markdown(report)

    assert "Read-only snapshot" in markdown
    assert "Confirm the matching repository, merged PR, live-apply receipt" in markdown
    assert "`ws-one`" in markdown


def test_changed_active_shard_requires_exact_reference_fields(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    base_ref = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    shard = tmp_path / "workstreams" / "active" / "ws-new.yaml"
    shard.parent.mkdir(parents=True)
    shard.write_text("id: ws-new\nrepositories: [org/repo]\n", encoding="utf-8")
    assert "pull_requests" in validate_new_workstream_metadata(tmp_path, base_ref)[0]

    shard.write_text("id: ws-new\nrepositories: [org/repo]\npull_requests: []\n", encoding="utf-8")
    assert validate_new_workstream_metadata(tmp_path, base_ref) == []
    subprocess.run(["git", "-C", str(tmp_path), "add", str(shard)], check=True)

    shard.write_text("id: ws-new\nrepositories: [org/repo]\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(shard)], check=True)
    failures = validate_new_workstream_metadata(tmp_path, base_ref)
    assert failures and "pull_requests" in failures[0]


def test_changed_file_manifest_works_without_a_git_base_ref(tmp_path: Path, monkeypatch) -> None:
    shard = tmp_path / "workstreams" / "active" / "ws-new.yaml"
    shard.parent.mkdir(parents=True)
    shard.write_text("id: ws-new\nrepositories: [org/repo]\npull_requests: []\n", encoding="utf-8")
    monkeypatch.setenv("LV3_VALIDATION_CHANGED_FILES_JSON", json.dumps(["workstreams/active/ws-new.yaml"]))

    assert validate_new_workstream_metadata(tmp_path, "missing/origin-main") == []
