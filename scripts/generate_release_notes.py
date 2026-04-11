#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from controller_automation_toolkit import emit_cli_error, repo_path
from platform.root_summary import (
    ReleaseNoteRecord,
    collect_release_note_records,
    enforce_line_budget,
    group_release_note_records_by_year,
    load_root_summary_budgets,
    relative_markdown_link,
    release_archive_page_path,
    split_recent_and_archived,
)


REPO_ROOT = repo_path()
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
    release_date = date.today().isoformat() if include_version else None
    return [
        record.version
        for record in collect_release_note_records(
            RELEASE_NOTES_DIR,
            include_version=include_version,
            include_released_on=release_date,
        )
    ]


def collect_changelog_release_versions(changelog_text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"\[(\d+\.\d+\.\d+) release notes\]\(", changelog_text)}


def render_release_note_link(version: str, *, from_release_index: bool) -> str:
    path = f"{version}.md" if from_release_index else f"docs/release-notes/{version}.md"
    return f"- [{version} release notes]({path})"


def render_release_index_entry(version: str) -> str:
    return f"- [{version}]({version}.md)"


def render_release_archive_section(
    archived_records: list[ReleaseNoteRecord],
    *,
    source_path: Path,
    archive_index_path: Path,
) -> str:
    lines = ["## Release Archives", ""]
    if not archived_records:
        lines.append("- No historical release-note indexes have rolled out yet.")
        return "\n".join(lines)

    lines.append(
        "- "
        + relative_markdown_link(
            "Release note archives",
            from_path=source_path,
            target_path=archive_index_path,
        )
    )
    for year, records in group_release_note_records_by_year(archived_records):
        lines.append(
            "- "
            + relative_markdown_link(
                f"{year} ({len(records)} releases)",
                from_path=source_path,
                target_path=release_archive_page_path(archive_index_path, year),
            )
        )
    return "\n".join(lines)


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


def render_release_index_documents(
    index_text: str,
    *,
    include_version: str | None = None,
    include_released_on: str | None = None,
) -> dict[Path, str]:
    budgets = load_root_summary_budgets()
    if RELEASES_HEADER not in index_text:
        raise ValueError("docs/release-notes/README.md must contain a '## Releases' section")
    before, _header, _existing = index_text.partition(RELEASES_HEADER)
    archive_index_path = REPO_ROOT / budgets.release_notes_index.archive_index_path
    records = collect_release_note_records(
        RELEASE_NOTES_DIR,
        include_version=include_version,
        include_released_on=include_released_on,
    )
    recent_records, archived_records = split_recent_and_archived(
        records,
        recent_limit=budgets.release_notes_index.recent_entries,
    )
    recent_lines = "\n".join(render_release_index_entry(record.version) for record in recent_records)
    if not recent_lines:
        recent_lines = "- No release notes have been cut yet."
    root_text = (
        f"{before.rstrip()}\n\n"
        f"{RELEASES_HEADER}"
        f"{recent_lines}\n\n"
        f"{render_release_archive_section(archived_records, source_path=RELEASE_NOTES_INDEX_PATH, archive_index_path=archive_index_path)}\n"
    )
    enforce_line_budget(
        root_text,
        label="docs/release-notes/README.md",
        max_lines=budgets.release_notes_index.max_lines,
    )

    documents = {
        RELEASE_NOTES_INDEX_PATH: root_text,
        archive_index_path: render_release_archive_index(archived_records, archive_index_path=archive_index_path),
    }
    for year, year_records in group_release_note_records_by_year(archived_records):
        documents[release_archive_page_path(archive_index_path, year)] = render_release_archive_year_page(
            year,
            year_records,
            archive_index_path=archive_index_path,
        )
    return documents


def render_release_archive_index(
    archived_records: list[ReleaseNoteRecord],
    *,
    archive_index_path: Path,
) -> str:
    lines = [
        "# Release Note Archives",
        "",
        "This generated index collects older release-note links after they roll out of the root summaries.",
        "",
    ]
    if not archived_records:
        lines.extend(["## Archived Years", "", "- No archived release-note indexes have rolled out yet.", ""])
        return "\n".join(lines)

    lines.extend(["## Archived Years", ""])
    for year, records in group_release_note_records_by_year(archived_records):
        lines.append(
            "- "
            + relative_markdown_link(
                f"{year} ({len(records)} releases)",
                from_path=archive_index_path,
                target_path=release_archive_page_path(archive_index_path, year),
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_release_archive_year_page(
    year: str,
    records: list[ReleaseNoteRecord],
    *,
    archive_index_path: Path,
) -> str:
    page_path = release_archive_page_path(archive_index_path, year)
    lines = [
        f"# {year} Release Notes",
        "",
        "- "
        + relative_markdown_link(
            "Release note archives",
            from_path=page_path,
            target_path=archive_index_path,
        ),
        "",
        "## Releases",
        "",
    ]
    for record in records:
        lines.append(
            "- "
            + relative_markdown_link(record.version, from_path=page_path, target_path=record.path)
            + f" ({record.released_on})"
        )
    lines.append("")
    return "\n".join(lines)


def render_changelog_release_sections(
    *,
    include_version: str | None = None,
    include_released_on: str | None = None,
    legacy_versions: set[str] | None = None,
) -> str:
    budgets = load_root_summary_budgets()
    archive_index_path = REPO_ROOT / budgets.changelog.archive_index_path
    records = collect_release_note_records(
        RELEASE_NOTES_DIR,
        include_version=include_version,
        include_released_on=include_released_on,
    )
    latest_record = records[:1]
    previous_records, archived_records = split_recent_and_archived(
        records[1:],
        recent_limit=budgets.changelog.previous_release_entries,
    )
    current_versions = {record.version for record in records}
    legacy_only_versions = sorted((legacy_versions or set()) - current_versions, key=parse_semver, reverse=True)

    lines = ["## Latest Release", ""]
    if latest_record:
        lines.append(render_release_note_link(latest_record[0].version, from_release_index=False))
    else:
        lines.append("- No release notes have been cut yet.")

    lines.extend(["", "## Previous Releases", ""])
    if previous_records:
        lines.extend(render_release_note_link(record.version, from_release_index=False) for record in previous_records)
    if legacy_only_versions:
        lines.extend(render_release_note_link(version, from_release_index=False) for version in legacy_only_versions)
    if not previous_records and not legacy_only_versions:
        lines.append("- No previous release notes have rolled out yet.")

    lines.extend(
        [
            "",
            render_release_archive_section(
                archived_records,
                source_path=CHANGELOG_PATH,
                archive_index_path=archive_index_path,
            ),
            "",
        ]
    )
    return "\n".join(lines)


def refresh_changelog_release_sections(
    changelog_text: str,
    *,
    include_version: str | None = None,
    include_released_on: str | None = None,
) -> str:
    match = re.search(r"^## Latest Release\s*$", changelog_text, re.MULTILINE)
    if not match:
        raise ValueError("changelog.md must contain a '## Latest Release' section")
    updated = changelog_text[: match.start()] + render_changelog_release_sections(
        include_version=include_version,
        include_released_on=include_released_on,
        legacy_versions=collect_changelog_release_versions(changelog_text),
    )
    enforce_line_budget(updated, label="changelog.md", max_lines=load_root_summary_budgets().changelog.max_lines)
    return updated


def update_changelog_for_release(changelog_text: str, version: str, *, released_on: str | None = None) -> str:
    match = UNRELEASED_PATTERN.search(changelog_text)
    if not match:
        raise ValueError("failed to clear the changelog Unreleased section")
    updated = changelog_text[: match.start()] + f"{match.group(1)}{match.group(3)}" + changelog_text[match.end() :]
    if "## Unreleased" not in updated:
        raise ValueError("failed to clear the changelog Unreleased section")
    return refresh_changelog_release_sections(
        updated,
        include_version=version,
        include_released_on=released_on or date.today().isoformat(),
    )


def update_release_notes_index(index_text: str, version: str) -> str:
    return render_release_index_documents(
        index_text,
        include_version=version,
        include_released_on=date.today().isoformat(),
    )[RELEASE_NOTES_INDEX_PATH]


def write_root_summary_documents(
    *,
    include_version: str | None = None,
    include_released_on: str | None = None,
) -> dict[Path, str]:
    rendered = render_release_index_documents(
        RELEASE_NOTES_INDEX_PATH.read_text(encoding="utf-8"),
        include_version=include_version,
        include_released_on=include_released_on,
    )
    rendered[CHANGELOG_PATH] = refresh_changelog_release_sections(
        CHANGELOG_PATH.read_text(encoding="utf-8"),
        include_version=include_version,
        include_released_on=include_released_on,
    )
    for path, text in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return rendered


def check_root_summary_documents() -> list[Path]:
    rendered = render_release_index_documents(RELEASE_NOTES_INDEX_PATH.read_text(encoding="utf-8"))
    rendered[CHANGELOG_PATH] = refresh_changelog_release_sections(CHANGELOG_PATH.read_text(encoding="utf-8"))
    stale_paths = []
    for path, expected in rendered.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            stale_paths.append(path)
    return stale_paths


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
    rendered_indexes = render_release_index_documents(
        RELEASE_NOTES_INDEX_PATH.read_text(encoding="utf-8"),
        include_version=version,
        include_released_on=release_date,
    )
    for path, text in rendered_indexes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return versioned_rendered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate structured release notes from changelog.md.")
    parser.add_argument("--version", help="Release version to render.")
    parser.add_argument(
        "--platform-impact",
        default="no live platform version bump; this release updates repository automation, release metadata, and operator tooling only",
        help="One-line platform impact summary to append to the release notes.",
    )
    parser.add_argument("--released-on", default=date.today().isoformat(), help="Release date in YYYY-MM-DD format.")
    parser.add_argument("--write", action="store_true", help="Write RELEASE.md and docs/release-notes/<version>.md.")
    parser.add_argument(
        "--write-root-summaries",
        action="store_true",
        help="Refresh changelog release sections plus release-note archive indexes from current release-note files.",
    )
    parser.add_argument(
        "--check-root-summaries",
        action="store_true",
        help="Verify changelog release sections plus release-note archive indexes are current.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.write_root_summaries or args.check_root_summaries:
            if args.write_root_summaries and args.check_root_summaries:
                raise ValueError("choose exactly one of --write-root-summaries or --check-root-summaries")
            stale_paths = check_root_summary_documents()
            if args.write_root_summaries:
                rendered = write_root_summary_documents()
                print(
                    "Updated root summary documents: "
                    + ", ".join(str(path.relative_to(REPO_ROOT)) for path in sorted(rendered))
                )
                return 0
            if stale_paths:
                print(
                    "Root summary documents are stale. Run "
                    "'uv run python scripts/generate_release_notes.py --write-root-summaries' or 'make generate-status-docs'. "
                    f"Stale paths: {', '.join(str(path.relative_to(REPO_ROOT)) for path in stale_paths)}"
                )
                return 2
            print("Root summary documents OK")
            return 0

        if not args.version:
            raise ValueError("--version is required unless --write-root-summaries or --check-root-summaries is used")
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
    except Exception as exc:
        return emit_cli_error("release notes", exc)


if __name__ == "__main__":
    raise SystemExit(main())
