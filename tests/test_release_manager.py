from __future__ import annotations

import json
from pathlib import Path

import pytest

import controller_automation_toolkit as toolkit
import generate_release_notes
import release_manager


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture()
def release_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write(tmp_path / "VERSION", "0.1.0\n")
    write(
        tmp_path / "versions" / "stack.yaml",
        """
schema_version: 1.0.0
repo_version: 0.1.0
platform_version: 0.0.1
release_tracks:
  delivery_model:
    mode: parallel_workstreams
    branch_prefix: codex/
  repo_versioning:
    current: 0.1.0
    meaning: repo
  platform_versioning:
    current: 0.0.1
    meaning: platform
""".strip()
        + "\n",
    )
    write(
        tmp_path / "changelog.md",
        """# Changelog

## Unreleased

- implemented ADR 0110
- added release readiness reporting

## Latest Release

- [0.1.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.1.0.md)
""",
    )
    write(
        tmp_path / "docs" / "release-notes" / "README.md",
        """# Release Notes

## Releases

- [0.1.0](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.1.0.md)
""",
    )
    write(tmp_path / "docs" / "upgrade" / "v1.md", "# Upgrade Guide\n")
    write(
        tmp_path / "workstreams.yaml",
        f"""
release_policy:
  breaking_change_criteria: {tmp_path / "config" / "version-semantics.json"}
workstreams:
  - id: adr-0110-platform-versioning
    status: merged
""".strip()
        + "\n",
    )
    write(
        tmp_path / "config" / "version-semantics.json",
        json.dumps(
            {
                "schema_version": "1.0.0",
                "repository_versioning": {
                    "major": {"meaning": "major", "triggers": ["a"]},
                    "minor": {"meaning": "minor", "triggers": ["b"]},
                    "patch": {"meaning": "patch", "triggers": ["c"]},
                },
                "breaking_change_criteria": [{"id": "catalog", "surface": "config/x", "description": "x"}],
                "release_artifacts": {
                    "working_section": "Unreleased",
                    "version_file": "VERSION",
                    "changelog_path": "changelog.md",
                    "root_release_notes": "RELEASE.md",
                    "release_notes_dir": "docs/release-notes",
                    "release_notes_index": "docs/release-notes/README.md",
                    "upgrade_guides_dir": "docs/upgrade",
                    "git_tag_prefix": "v",
                },
                "release_gates": {"blocking_workstream_statuses": ["in_progress"]},
                "upgrade_policy": {
                    "minor_version_skip_supported": True,
                    "major_version_skip_supported": False,
                    "rules": [
                        {
                            "source": "0.x",
                            "target": "1.0.0",
                            "operator_action_required": False,
                            "notes": "none",
                        }
                    ],
                },
                "readiness_targets": {
                    "1.0.0": {
                        "adr_window": {
                            "start": 1,
                            "end": 2,
                            "required_statuses": ["Accepted"],
                            "required_implementation_statuses": ["Implemented"],
                        },
                        "required_services": [],
                        "required_slos": [],
                        "slo_report_path": "receipts/slo-reports/latest.json",
                        "restore_verification": {
                            "receipt_dir": "receipts/restore-verifications",
                            "required_consecutive_passes": 2,
                        },
                        "dr_table_top_review": {"receipt_dir": "receipts/dr-table-top-reviews"},
                    }
                },
            },
            indent=2,
        )
        + "\n",
    )
    write(
        tmp_path / "docs" / "adr" / "0001-example.md",
        """# ADR 0001: Example

- Status: Accepted
- Implementation Status: Implemented
""",
    )
    write(
        tmp_path / "docs" / "adr" / "0002-example.md",
        """# ADR 0002: Example

- Status: Accepted
- Implementation Status: Implemented
""",
    )

    monkeypatch.setattr(toolkit, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release_manager, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release_manager, "VERSION_PATH", tmp_path / "VERSION")
    monkeypatch.setattr(release_manager, "STACK_PATH", tmp_path / "versions" / "stack.yaml")
    monkeypatch.setattr(release_manager, "WORKSTREAMS_PATH", tmp_path / "workstreams.yaml")
    monkeypatch.setattr(release_manager, "ADR_DIR", tmp_path / "docs" / "adr")
    monkeypatch.setattr(release_manager, "VERSION_SEMANTICS_PATH", tmp_path / "config" / "version-semantics.json")
    monkeypatch.setattr(release_manager, "CHANGELOG_PATH", tmp_path / "changelog.md")
    monkeypatch.setattr(release_manager, "RELEASE_NOTES_INDEX_PATH", tmp_path / "docs" / "release-notes" / "README.md")

    monkeypatch.setattr(generate_release_notes, "CHANGELOG_PATH", tmp_path / "changelog.md")
    monkeypatch.setattr(generate_release_notes, "RELEASE_NOTES_INDEX_PATH", tmp_path / "docs" / "release-notes" / "README.md")
    monkeypatch.setattr(generate_release_notes, "ROOT_RELEASE_NOTES_PATH", tmp_path / "RELEASE.md")
    monkeypatch.setattr(generate_release_notes, "RELEASE_NOTES_DIR", tmp_path / "docs" / "release-notes")
    return tmp_path


def test_release_status_snapshot_reports_blockers(release_repo: Path) -> None:
    (release_repo / "workstreams.yaml").write_text(
        (release_repo / "workstreams.yaml").read_text().replace("status: merged", "status: in_progress")
    )

    snapshot = release_manager.build_release_status_snapshot(timeout=0)

    assert snapshot["release_blockers"]["status"] == "blocked"
    assert snapshot["criteria"][0]["detail"].startswith("2/2 implemented")


def test_release_cut_updates_core_release_files(release_repo: Path) -> None:
    exit_code = release_manager.main(
        [
            "--bump",
            "patch",
            "--platform-impact",
            "no live platform version bump; repository-only release",
        ]
    )

    assert exit_code == 0
    assert (release_repo / "VERSION").read_text().strip() == "0.1.1"
    assert "repo_version: 0.1.1" in (release_repo / "versions" / "stack.yaml").read_text()
    changelog = (release_repo / "changelog.md").read_text()
    assert "0.1.1 release notes" in changelog
    assert "implemented ADR 0110" not in changelog
    assert (release_repo / "RELEASE.md").exists()
    assert (release_repo / "docs" / "release-notes" / "0.1.1.md").exists()
    assert "[0.1.1](" in (release_repo / "docs" / "release-notes" / "README.md").read_text()
