from __future__ import annotations

from pathlib import Path

import generate_release_notes as notes


def test_extract_unreleased_items_and_update_changelog() -> None:
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

    updated = notes.update_changelog_for_release(changelog, "0.97.0")
    assert "## Unreleased\n\n## Latest Release" in updated
    assert "0.97.0 release notes" in updated
    assert "added release manager" not in updated
    assert "## Previous Releases" in updated
    assert "0.96.0 release notes" in updated
    assert "0.95.0 release notes" in updated


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

    monkeypatch.setattr(notes, "RELEASE_NOTES_DIR", tmp_path / "docs" / "release-notes")
    (notes.RELEASE_NOTES_DIR / "0.1.0.md").parent.mkdir(parents=True, exist_ok=True)
    (notes.RELEASE_NOTES_DIR / "0.1.0.md").write_text("# Release 0.1.0\n", encoding="utf-8")

    updated = notes.update_changelog_for_release(changelog, "0.1.1")

    assert "0.1.1 release notes" in updated
    assert "0.1.0 release notes" in updated
    assert "0.0.9 release notes" in updated
