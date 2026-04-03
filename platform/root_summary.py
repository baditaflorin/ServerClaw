from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from platform.repo import load_yaml, repo_path


ROOT_SUMMARY_BUDGETS_PATH = repo_path("config", "root-summary-budgets.yaml")
SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RELEASE_DATE_PATTERN = re.compile(r"^- Date:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
ISO_RECEIPT_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
TIMESTAMP_RECEIPT_PREFIX = re.compile(r"^(\d{8}T\d{6}Z)")


@dataclass(frozen=True)
class ReadmeSummaryBudget:
    max_lines: int
    recent_live_apply_entries: int
    live_apply_history_path: Path
    recent_merged_workstream_entries: int
    merged_workstream_history_path: Path


@dataclass(frozen=True)
class ChangelogSummaryBudget:
    max_lines: int
    previous_release_entries: int
    archive_index_path: Path


@dataclass(frozen=True)
class ReleaseNotesIndexBudget:
    max_lines: int
    recent_entries: int
    archive_index_path: Path


@dataclass(frozen=True)
class RootSummaryBudgets:
    readme: ReadmeSummaryBudget
    changelog: ChangelogSummaryBudget
    release_notes_index: ReleaseNotesIndexBudget


@dataclass(frozen=True)
class ReleaseNoteRecord:
    version: str
    released_on: str
    path: Path

    @property
    def year(self) -> str:
        return self.released_on[:4]


@dataclass(frozen=True)
class LiveApplyEvidenceRecord:
    capability: str
    receipt_id: str
    sort_key: str


@dataclass(frozen=True)
class MergedWorkstreamRecord:
    workstream_id: str
    adr: str
    title: str
    status: str
    doc_path: Path
    included_in_repo_version: str | None


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


def _require_repo_relative_path(value: Any, path: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    normalized = value.strip().replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError(f"{path} must be repository-relative")
    return Path(normalized)


def load_root_summary_budgets(path: Path | None = None) -> RootSummaryBudgets:
    payload = _require_mapping(load_yaml(path or ROOT_SUMMARY_BUDGETS_PATH), "config/root-summary-budgets.yaml")
    schema_version = payload.get("schema_version")
    if schema_version != "1.0.0":
        raise ValueError("config/root-summary-budgets.yaml must declare schema_version 1.0.0")

    readme = _require_mapping(payload.get("readme"), "config/root-summary-budgets.yaml.readme")
    readme_live_apply = _require_mapping(
        readme.get("live_apply_evidence"),
        "config/root-summary-budgets.yaml.readme.live_apply_evidence",
    )
    readme_workstreams = _require_mapping(
        readme.get("merged_workstreams"),
        "config/root-summary-budgets.yaml.readme.merged_workstreams",
    )

    changelog = _require_mapping(payload.get("changelog"), "config/root-summary-budgets.yaml.changelog")
    release_notes_index = _require_mapping(
        payload.get("release_notes_index"),
        "config/root-summary-budgets.yaml.release_notes_index",
    )

    return RootSummaryBudgets(
        readme=ReadmeSummaryBudget(
            max_lines=_require_positive_int(readme.get("max_lines"), "config/root-summary-budgets.yaml.readme.max_lines"),
            recent_live_apply_entries=_require_positive_int(
                readme_live_apply.get("recent_entries"),
                "config/root-summary-budgets.yaml.readme.live_apply_evidence.recent_entries",
            ),
            live_apply_history_path=_require_repo_relative_path(
                readme_live_apply.get("history_path"),
                "config/root-summary-budgets.yaml.readme.live_apply_evidence.history_path",
            ),
            recent_merged_workstream_entries=_require_positive_int(
                readme_workstreams.get("recent_entries"),
                "config/root-summary-budgets.yaml.readme.merged_workstreams.recent_entries",
            ),
            merged_workstream_history_path=_require_repo_relative_path(
                readme_workstreams.get("history_path"),
                "config/root-summary-budgets.yaml.readme.merged_workstreams.history_path",
            ),
        ),
        changelog=ChangelogSummaryBudget(
            max_lines=_require_positive_int(
                changelog.get("max_lines"),
                "config/root-summary-budgets.yaml.changelog.max_lines",
            ),
            previous_release_entries=_require_positive_int(
                changelog.get("previous_release_entries"),
                "config/root-summary-budgets.yaml.changelog.previous_release_entries",
            ),
            archive_index_path=_require_repo_relative_path(
                changelog.get("archive_index_path"),
                "config/root-summary-budgets.yaml.changelog.archive_index_path",
            ),
        ),
        release_notes_index=ReleaseNotesIndexBudget(
            max_lines=_require_positive_int(
                release_notes_index.get("max_lines"),
                "config/root-summary-budgets.yaml.release_notes_index.max_lines",
            ),
            recent_entries=_require_positive_int(
                release_notes_index.get("recent_entries"),
                "config/root-summary-budgets.yaml.release_notes_index.recent_entries",
            ),
            archive_index_path=_require_repo_relative_path(
                release_notes_index.get("archive_index_path"),
                "config/root-summary-budgets.yaml.release_notes_index.archive_index_path",
            ),
        ),
    )


def count_lines(text: str) -> int:
    stripped = text.rstrip("\n")
    if not stripped:
        return 0
    return len(stripped.splitlines())


def enforce_line_budget(text: str, *, label: str, max_lines: int) -> None:
    actual = count_lines(text)
    if actual > max_lines:
        raise ValueError(f"{label} exceeds its {max_lines}-line budget after regeneration ({actual} lines)")


def relative_markdown_link(label: str, *, from_path: Path, target_path: Path) -> str:
    relative = os.path.relpath(target_path, start=from_path.parent).replace(os.sep, "/")
    return f"[{label}]({relative})"


def collect_release_note_records(
    release_notes_dir: Path,
    *,
    include_version: str | None = None,
    include_released_on: str | None = None,
) -> list[ReleaseNoteRecord]:
    records: list[ReleaseNoteRecord] = []
    seen_versions: set[str] = set()
    for path in release_notes_dir.glob("*.md"):
        if path.name == "README.md":
            continue
        version = path.stem
        match = RELEASE_DATE_PATTERN.search(path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"{path} must include a '- Date: YYYY-MM-DD' metadata line")
        released_on = match.group(1)
        if not DATE_PATTERN.fullmatch(released_on):
            raise ValueError(f"{path} must use YYYY-MM-DD release metadata")
        records.append(ReleaseNoteRecord(version=version, released_on=released_on, path=path))
        seen_versions.add(version)

    if include_version and include_version not in seen_versions:
        if include_released_on is None:
            raise ValueError("include_released_on is required when including a synthetic release note")
        if not DATE_PATTERN.fullmatch(include_released_on):
            raise ValueError("include_released_on must use YYYY-MM-DD format")
        records.append(
            ReleaseNoteRecord(
                version=include_version,
                released_on=include_released_on,
                path=release_notes_dir / f"{include_version}.md",
            )
        )

    return sorted(records, key=lambda record: parse_semver(record.version), reverse=True)


def split_recent_and_archived(
    records: Sequence[ReleaseNoteRecord],
    *,
    recent_limit: int,
) -> tuple[list[ReleaseNoteRecord], list[ReleaseNoteRecord]]:
    recent = list(records[:recent_limit])
    archived = list(records[recent_limit:])
    return recent, archived


def group_release_note_records_by_year(records: Sequence[ReleaseNoteRecord]) -> list[tuple[str, list[ReleaseNoteRecord]]]:
    grouped: dict[str, list[ReleaseNoteRecord]] = {}
    for record in records:
        grouped.setdefault(record.year, []).append(record)
    return sorted(grouped.items(), key=lambda item: item[0], reverse=True)


def release_archive_page_path(archive_index_path: Path, year: str) -> Path:
    return archive_index_path.parent / f"{year}.md"


def render_release_archive_overview(
    archived_records: Sequence[ReleaseNoteRecord],
    *,
    archive_index_path: Path,
) -> str:
    lines = [
        "# Release Note Archives",
        "",
        "This generated index collects release-note history that has rolled out of the root summaries.",
        "",
    ]
    if not archived_records:
        lines.extend(
            [
                "## Archived Years",
                "",
                "- No release-note history has rolled out yet.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["## Archived Years", ""])
    overview_path = archive_index_path
    for year, records in group_release_note_records_by_year(archived_records):
        lines.append(
            "- "
            + relative_markdown_link(
                f"{year} ({len(records)} releases)",
                from_path=overview_path,
                target_path=release_archive_page_path(archive_index_path, year),
            )
        )
    lines.append("")
    return "\n".join(lines)


def render_release_archive_year_page(
    year: str,
    records: Sequence[ReleaseNoteRecord],
    *,
    archive_index_path: Path,
) -> str:
    page_path = release_archive_page_path(archive_index_path, year)
    lines = [
        f"# {year} Release Notes",
        "",
        f"- Archive index: {relative_markdown_link('Release note archives', from_path=page_path, target_path=archive_index_path)}",
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


def _receipt_sort_key(receipt_id: str) -> str:
    timestamp_match = TIMESTAMP_RECEIPT_PREFIX.match(receipt_id)
    if timestamp_match:
        parsed = datetime.strptime(timestamp_match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    date_match = ISO_RECEIPT_PREFIX.match(receipt_id)
    if date_match:
        parsed_date = date.fromisoformat(date_match.group(1))
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    return ""


def collect_live_apply_evidence_records(latest_receipts: Mapping[str, str]) -> list[LiveApplyEvidenceRecord]:
    records = [
        LiveApplyEvidenceRecord(capability=str(capability), receipt_id=str(receipt_id), sort_key=_receipt_sort_key(str(receipt_id)))
        for capability, receipt_id in latest_receipts.items()
    ]
    return sorted(records, key=lambda record: (record.sort_key, record.capability), reverse=True)


def collect_merged_workstream_records(workstreams: Sequence[Mapping[str, Any]]) -> list[MergedWorkstreamRecord]:
    records: list[MergedWorkstreamRecord] = []
    for workstream in workstreams:
        status = str(workstream.get("status") or "").strip()
        if status not in {"merged", "live_applied"}:
            continue
        canonical_truth = workstream.get("canonical_truth") or {}
        included = canonical_truth.get("included_in_repo_version")
        records.append(
            MergedWorkstreamRecord(
                workstream_id=str(workstream.get("id") or "").strip(),
                adr=str(workstream.get("adr") or "").strip(),
                title=str(workstream.get("title") or "").strip(),
                status=status,
                doc_path=Path(str(workstream.get("doc") or "").strip()),
                included_in_repo_version=str(included).strip() if included is not None else None,
            )
        )

    def sort_key(record: MergedWorkstreamRecord) -> tuple[int, tuple[int, int, int], int, str]:
        is_unreleased = 1 if record.included_in_repo_version is None else 0
        version_key = parse_semver(record.included_in_repo_version) if record.included_in_repo_version else (0, 0, 0)
        adr_key = int(record.adr) if record.adr.isdigit() else 0
        return (is_unreleased, version_key, adr_key, record.workstream_id)

    return sorted(records, key=sort_key, reverse=True)
