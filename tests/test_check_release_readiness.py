from __future__ import annotations

from pathlib import Path

import check_release_readiness as readiness


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_changelog_entry_accepts_cut_release_notes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(readiness, "REPO_ROOT", tmp_path)
    write(tmp_path / "VERSION", "1.2.3\n")
    write(
        tmp_path / "changelog.md",
        """# Changelog

## Unreleased

## Latest Release
""",
    )
    write(
        tmp_path / "docs" / "release-notes" / "1.2.3.md",
        """# Release 1.2.3

## Summary
- shipped the release-worthy change

## Platform Impact
- platform state is current
""",
    )

    result = readiness.check_changelog_entry()

    assert result["passed"] is True
    assert "release notes for 1.2.3" in result["message"]


def test_changelog_entry_rejects_placeholder_release_notes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(readiness, "REPO_ROOT", tmp_path)
    write(tmp_path / "VERSION", "1.2.3\n")
    write(
        tmp_path / "changelog.md",
        """# Changelog

## Unreleased

## Latest Release
""",
    )
    write(
        tmp_path / "docs" / "release-notes" / "1.2.3.md",
        """# Release 1.2.3

## Summary
- No changelog notes were present in `## Unreleased` at release time.

## Platform Impact
- platform state is current
""",
    )

    result = readiness.check_changelog_entry()

    assert result["passed"] is False
    assert result["message"] == "No entry under ## Unreleased in changelog.md"
