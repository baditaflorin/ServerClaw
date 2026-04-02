#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from controller_automation_toolkit import emit_cli_error, repo_path


CHANGELOG_PATH = repo_path("changelog.md")
RELEASE_NOTES_INDEX_PATH = repo_path("docs", "release-notes", "README.md")
ROOT_RELEASE_NOTES_PATH = repo_path("RELEASE.md")
RELEASE_NOTES_DIR = repo_path("docs", "release-notes")
UNRELEASED_PATTERN = re.compile(
    r"(^## Unreleased\n)(.*?)(^\s*## Latest Release\s*$)",
    re.MULTILINE | re.DOTALL,
)
RELEASES_HEADER = "## Releases\n"


def parse_semver(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def collect_release_versions(include_version: str | None = None) -> list[str]:
    versions = {
        path.stem
        for path in RELEASE_NOTES_DIR.glob("*.md")
        if path.name != "README.md"
    }
    if include_version:
        versions.add(include_version)
    return sorted(versions, key=parse_semver, reverse=True)


def collect_changelog_release_versions(changelog_text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"\[(\d+\.\d+\.\d+) release notes\]\(", changelog_text)
    }


def render_release_note_link(version: str, *, from_release_index: bool) -> str:
    path = f"{version}.md" if from_release_index else f"docs/release-notes/{version}.md"
    return f"- [{version} release notes]({path})"


def render_release_index_entry(version: str) -> str:
    return f"- [{version}]({version}.md)"


def extract_unreleased_block(changelog_text: str) -> str:
    match = UNRELEASED_PATTERN.search(changelog_text)
    if not match:
        raise ValueError("changelog.md must contain a '## Unreleased' section before '## Latest Release'")
    return match.group(2).strip()


def extract_unreleased_items(changelog_text: str) -> list[str]:
    block = extract_unreleased_block(changelog_text)
    items = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def render_release_notes(
    version: str,
    *,
    released_on: str,
    notes: list[str],
    platform_impact: str,
    upgrade_guide_path: str | None = None,
) -> str:
    lines = [f"# Release {version}", "", f"- Date: {released_on}", "", "## Summary"]
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- No changelog notes were present in `## Unreleased` at release time.")

    lines.extend(["", "## Platform Impact", f"- {platform_impact}"])
    if upgrade_guide_path:
        lines.extend(["", "## Upgrade Guide", f"- [{upgrade_guide_path}]({upgrade_guide_path})"])
    lines.append("")
    return "\n".join(lines)


def update_changelog_for_release(changelog_text: str, version: str) -> str:
    match = UNRELEASED_PATTERN.search(changelog_text)
    if not match:
        raise ValueError("failed to clear the changelog Unreleased section")
    updated = changelog_text[: match.start()] + f"{match.group(1)}{match.group(3)}" + changelog_text[match.end() :]
    if "## Unreleased" not in updated:
        raise ValueError("failed to clear the changelog Unreleased section")
    versions = sorted(
        set(collect_release_versions(include_version=version)) | collect_changelog_release_versions(changelog_text),
        key=parse_semver,
        reverse=True,
    )
    latest = versions[0]
    previous = versions[1:]
    latest_block = "## Latest Release\n\n" + render_release_note_link(latest, from_release_index=False) + "\n"
    previous_lines = "\n".join(
        render_release_note_link(release_version, from_release_index=False)
        for release_version in previous
    )
    replacement = "## Previous Releases\n"
    if previous_lines:
        replacement += f"\n{previous_lines}\n"
    updated, count = re.subn(
        r"^## Latest Release\n.*?^## Previous Releases\n.*?(?=^\s*## |\Z)",
        latest_block + "\n" + replacement,
        updated,
        count=1,
        flags=re.MULTILINE | re.DOTALL,
    )
    if count != 1:
        raise ValueError("failed to rebuild the changelog release sections")
    return updated


def update_release_notes_index(index_text: str, version: str) -> str:
    if RELEASES_HEADER not in index_text:
        raise ValueError("docs/release-notes/README.md must contain a '## Releases' section")
    versions = collect_release_versions(include_version=version)
    release_lines = "\n".join(render_release_index_entry(release_version) for release_version in versions)
    before, _header, _existing = index_text.partition(RELEASES_HEADER)
    return f"{before}{RELEASES_HEADER}\n{release_lines}\n"


def write_release_artifacts(
    version: str,
    *,
    notes: list[str],
    platform_impact: str,
    released_on: str | None = None,
) -> str:
    release_date = released_on or date.today().isoformat()
    has_upgrade_guide = Path(repo_path("docs", "upgrade", "v1.md")).exists()
    root_upgrade_guide = "docs/upgrade/v1.md" if has_upgrade_guide else None
    versioned_upgrade_guide = "../upgrade/v1.md" if has_upgrade_guide else None
    root_rendered = render_release_notes(
        version,
        released_on=release_date,
        notes=notes,
        platform_impact=platform_impact,
        upgrade_guide_path=root_upgrade_guide,
    )
    versioned_rendered = render_release_notes(
        version,
        released_on=release_date,
        notes=notes,
        platform_impact=platform_impact,
        upgrade_guide_path=versioned_upgrade_guide,
    )
    ROOT_RELEASE_NOTES_PATH.write_text(root_rendered)
    RELEASE_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    (RELEASE_NOTES_DIR / f"{version}.md").write_text(versioned_rendered)
    RELEASE_NOTES_INDEX_PATH.write_text(
        update_release_notes_index(RELEASE_NOTES_INDEX_PATH.read_text(), version)
    )
    return versioned_rendered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate structured release notes from changelog.md.")
    parser.add_argument("--version", required=True, help="Release version to render.")
    parser.add_argument(
        "--platform-impact",
        required=True,
        help="One-line platform impact summary to append to the release notes.",
    )
    parser.add_argument("--released-on", default=date.today().isoformat(), help="Release date in YYYY-MM-DD format.")
    parser.add_argument("--write", action="store_true", help="Write RELEASE.md and docs/release-notes/<version>.md.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        notes = extract_unreleased_items(CHANGELOG_PATH.read_text())
        rendered = render_release_notes(
            args.version,
            released_on=args.released_on,
            notes=notes,
            platform_impact=args.platform_impact,
            upgrade_guide_path="docs/upgrade/v1.md" if repo_path("docs", "upgrade", "v1.md").exists() else None,
        )
        if args.write:
            write_release_artifacts(
                args.version,
                notes=notes,
                platform_impact=args.platform_impact,
                released_on=args.released_on,
            )
        else:
            print(rendered)
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("release notes", exc)


if __name__ == "__main__":
    raise SystemExit(main())
