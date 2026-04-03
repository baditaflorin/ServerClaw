from __future__ import annotations

from pathlib import Path

import generate_release_notes as notes
import platform.root_summary as root_summary


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_budget(path: Path, *, previous_release_entries: int = 2, recent_release_entries: int = 3) -> None:
    write(
        path,
        f"""schema_version: 1.0.0
readme:
  max_lines: 320
  live_apply_evidence:
    recent_entries: 20
    history_path: docs/status/history/live-apply-evidence.md
  merged_workstreams:
    recent_entries: 25
    history_path: docs/status/history/merged-workstreams.md
changelog:
  max_lines: 90
  previous_release_entries: {previous_release_entries}
  archive_index_path: docs/release-notes/index/README.md
release_notes_index:
  max_lines: 90
  recent_entries: {recent_release_entries}
  archive_index_path: docs/release-notes/index/README.md
""",
    )


def test_extract_unreleased_items_and_update_changelog(tmp_path: Path) -> None:
    changelog = """# Changelog

## Unreleased

- added release manager
- added upgrade guide

## Latest Release

- [0.96.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.96.0.md)

## Previous Releases

- [0.95.0 release notes](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/release-notes/0.95.0.md)
"""

    assert notes.extract_unreleased_items(changelog) == [
        "added release manager",
        "added upgrade guide",
    ]

    budget_path = tmp_path / "config" / "root-summary-budgets.yaml"
    write_budget(budget_path, previous_release_entries=5, recent_release_entries=5)
    original_budget_path = root_summary.ROOT_SUMMARY_BUDGETS_PATH
    original_release_dir = notes.RELEASE_NOTES_DIR
    try:
        root_summary.ROOT_SUMMARY_BUDGETS_PATH = budget_path
        notes.RELEASE_NOTES_DIR = budget_path.parent / "docs" / "release-notes"
        write(notes.RELEASE_NOTES_DIR / "0.96.0.md", "# Release 0.96.0\n\n- Date: 2026-03-20\n")
        updated = notes.update_changelog_for_release(changelog, "0.97.0", released_on="2026-03-21")
    finally:
        root_summary.ROOT_SUMMARY_BUDGETS_PATH = original_budget_path
        notes.RELEASE_NOTES_DIR = original_release_dir

    assert "## Unreleased\n\n## Latest Release" in updated
    assert "0.97.0 release notes" in updated
    assert "added release manager" not in updated
    assert "## Previous Releases" in updated
    assert "0.96.0 release notes" in updated
    assert "0.95.0 release notes" in updated


def test_update_changelog_rolls_older_releases_into_archive_links(
    monkeypatch, tmp_path: Path
) -> None:
    changelog = """# Changelog

## Unreleased

- added release manager

## Latest Release

- [0.1.3 release notes](docs/release-notes/0.1.3.md)

## Previous Releases
"""

    budget_path = tmp_path / "config" / "root-summary-budgets.yaml"
    write_budget(budget_path, previous_release_entries=2, recent_release_entries=2)
    monkeypatch.setattr(root_summary, "ROOT_SUMMARY_BUDGETS_PATH", budget_path)
    monkeypatch.setattr(notes, "CHANGELOG_PATH", tmp_path / "changelog.md")
    monkeypatch.setattr(notes, "RELEASE_NOTES_DIR", tmp_path / "docs" / "release-notes")
    monkeypatch.setattr(notes, "RELEASE_NOTES_INDEX_PATH", tmp_path / "docs" / "release-notes" / "README.md")
    monkeypatch.setattr(notes, "REPO_ROOT", tmp_path)

    write(notes.RELEASE_NOTES_DIR / "0.1.1.md", "# Release 0.1.1\n\n- Date: 2025-12-31\n")
    write(notes.RELEASE_NOTES_DIR / "0.1.2.md", "# Release 0.1.2\n\n- Date: 2026-01-02\n")
    write(notes.RELEASE_NOTES_DIR / "0.1.3.md", "# Release 0.1.3\n\n- Date: 2026-01-03\n")

    updated = notes.update_changelog_for_release(changelog, "0.1.4", released_on="2026-01-04")

    assert "- [0.1.4 release notes](docs/release-notes/0.1.4.md)" in updated
    assert "- [0.1.3 release notes](docs/release-notes/0.1.3.md)" in updated
    assert "- [0.1.2 release notes](docs/release-notes/0.1.2.md)" in updated
    assert "- [0.1.1 release notes](docs/release-notes/0.1.1.md)" not in updated
    assert "## Release Archives" in updated
    assert "(docs/release-notes/index/README.md)" in updated
    assert "(docs/release-notes/index/2025.md)" in updated


def test_render_release_notes_includes_structured_sections() -> None:
    rendered = notes.render_release_notes(
        "0.97.0",
        released_on="2026-03-23",
        notes=["implemented ADR 0110"],
        platform_impact="no live platform version bump",
        upgrade_guide_path="docs/upgrade/v1.md",
    )

    assert "# Release 0.97.0" in rendered
    assert "## Summary" in rendered
    assert "## Platform Impact" in rendered
    assert "## Upgrade Guide" in rendered


def test_update_changelog_preserves_historical_release_links_without_note_files(
    monkeypatch, tmp_path: Path
) -> None:
    changelog = """# Changelog

## Unreleased

- added release manager

## Latest Release

- [0.1.0 release notes](docs/release-notes/0.1.0.md)

## Previous Releases

- [0.0.9 release notes](docs/release-notes/0.0.9.md)
"""

    budget_path = tmp_path / "config" / "root-summary-budgets.yaml"
    write_budget(budget_path, previous_release_entries=5, recent_release_entries=5)
    monkeypatch.setattr(root_summary, "ROOT_SUMMARY_BUDGETS_PATH", budget_path)
    monkeypatch.setattr(notes, "RELEASE_NOTES_DIR", tmp_path / "docs" / "release-notes")
    (notes.RELEASE_NOTES_DIR / "0.1.0.md").parent.mkdir(parents=True, exist_ok=True)
    (notes.RELEASE_NOTES_DIR / "0.1.0.md").write_text("# Release 0.1.0\n\n- Date: 2026-01-01\n", encoding="utf-8")

    updated = notes.update_changelog_for_release(changelog, "0.1.1", released_on="2026-01-02")

    assert "0.1.1 release notes" in updated
    assert "0.1.0 release notes" in updated
    assert "0.0.9 release notes" in updated


def test_render_release_index_documents_rolls_older_versions_into_year_pages(
    monkeypatch, tmp_path: Path
) -> None:
    budget_path = tmp_path / "config" / "root-summary-budgets.yaml"
    write_budget(budget_path, previous_release_entries=3, recent_release_entries=2)
    monkeypatch.setattr(root_summary, "ROOT_SUMMARY_BUDGETS_PATH", budget_path)
    monkeypatch.setattr(notes, "RELEASE_NOTES_DIR", tmp_path / "docs" / "release-notes")
    monkeypatch.setattr(notes, "RELEASE_NOTES_INDEX_PATH", tmp_path / "docs" / "release-notes" / "README.md")
    monkeypatch.setattr(notes, "REPO_ROOT", tmp_path)

    write(
        notes.RELEASE_NOTES_INDEX_PATH,
        """# Release Notes

Versioned release notes live here after `Unreleased` is cut on `main`.

## Releases
""",
    )
    write(notes.RELEASE_NOTES_DIR / "0.1.0.md", "# Release 0.1.0\n\n- Date: 2025-12-31\n")
    write(notes.RELEASE_NOTES_DIR / "0.1.1.md", "# Release 0.1.1\n\n- Date: 2026-01-01\n")
    write(notes.RELEASE_NOTES_DIR / "0.1.2.md", "# Release 0.1.2\n\n- Date: 2026-01-02\n")
    write(notes.RELEASE_NOTES_DIR / "0.1.3.md", "# Release 0.1.3\n\n- Date: 2026-01-03\n")

    documents = notes.render_release_index_documents(notes.RELEASE_NOTES_INDEX_PATH.read_text(encoding="utf-8"))
    root_index = documents[notes.RELEASE_NOTES_INDEX_PATH]
    archive_overview = documents[tmp_path / "docs" / "release-notes" / "index" / "README.md"]
    archive_2025 = documents[tmp_path / "docs" / "release-notes" / "index" / "2025.md"]

    assert "- [0.1.3](0.1.3.md)" in root_index
    assert "- [0.1.2](0.1.2.md)" in root_index
    assert "- [0.1.1](0.1.1.md)" not in root_index
    assert "## Release Archives" in root_index
    assert "- [Release note archives](index/README.md)" in root_index
    assert "- [2025 (1 releases)](2025.md)" in archive_overview
    assert "- [0.1.0](../0.1.0.md) (2025-12-31)" in archive_2025
