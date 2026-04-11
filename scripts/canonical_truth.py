#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controller_automation_toolkit import README_PATH, emit_cli_error, load_yaml, repo_path
from platform.workstream_registry import (
    find_workstream,
    has_sharded_sources,
    load_workstreams as load_registry_workstreams,
    write_assembled_registry,
    write_workstream,
)


REPO_ROOT = repo_path()
VERSION_PATH = repo_path("VERSION")
CHANGELOG_PATH = repo_path("changelog.md")
STACK_PATH = repo_path("versions", "stack.yaml")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
RELEASE_CANDIDATE_STATUSES = {"ready_for_merge", "merged", "live_applied"}
LIVE_APPLIED_STATUS = "live_applied"
VALID_RELEASE_BUMPS = {"patch", "minor", "major"}
UNRELEASED_PATTERN = re.compile(r"(?ms)(^## Unreleased\n)(.*?)(?=^## )")
LATEST_RECEIPTS_PATTERN = re.compile(r"(?ms)(^live_apply_evidence:\n(?:  [^\n]*\n)*?  latest_receipts:\n)(.*?)(?=^\S)")
WORKSTREAM_BLOCK_PATTERN = r"(?ms)^  - id: {workstream_id}\n.*?(?=^  - id: |\Z)"
WORKSTREAM_RELEASE_BUMP_PATTERN = re.compile(r"(?m)^(      release_bump:\s*\S+\n)")
WORKSTREAM_INCLUDED_IN_REPO_VERSION_PATTERN = re.compile(r"(?m)^(      included_in_repo_version:\s*)(null|\S+)\n")


@dataclass(frozen=True)
class WorkstreamCanonicalTruth:
    workstream_id: str
    adr: str
    title: str
    status: str
    changelog_entry: str | None
    release_bump: str | None
    included_in_repo_version: str | None
    latest_receipts: dict[str, str]


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ValueError(f"invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())


def bump_semver(value: str, bump: str) -> str:
    major, minor, patch = parse_semver(value)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unsupported bump type: {bump}")


def _require_mapping(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping")
    return value


def _require_string(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_optional_semver(value: Any, *, path: str) -> str | None:
    if value is None:
        return None
    candidate = _require_string(value, path=path)
    parse_semver(candidate)
    return candidate


def load_workstream_canonical_truth(path: Path | None = None) -> list[WorkstreamCanonicalTruth]:
    resolved_path = path or WORKSTREAMS_PATH
    workstreams = load_registry_workstreams(compatibility_path=resolved_path, include_archive=True)

    result: list[WorkstreamCanonicalTruth] = []
    for index, workstream in enumerate(workstreams):
        workstream_path = f"workstreams.yaml.workstreams[{index}]"
        workstream_mapping = _require_mapping(workstream, path=workstream_path)
        workstream_id = _require_string(workstream_mapping.get("id"), path=f"{workstream_path}.id")
        adr = _require_string(workstream_mapping.get("adr"), path=f"{workstream_path}.adr")
        title = _require_string(workstream_mapping.get("title"), path=f"{workstream_path}.title")
        status = _require_string(workstream_mapping.get("status"), path=f"{workstream_path}.status")

        canonical_truth = workstream_mapping.get("canonical_truth")
        if canonical_truth is None:
            continue

        canonical_truth_mapping = _require_mapping(canonical_truth, path=f"{workstream_path}.canonical_truth")
        changelog_entry_value = canonical_truth_mapping.get("changelog_entry")
        changelog_entry = None
        if changelog_entry_value is not None:
            changelog_entry = _require_string(
                changelog_entry_value,
                path=f"{workstream_path}.canonical_truth.changelog_entry",
            )

        release_bump_value = canonical_truth_mapping.get("release_bump")
        release_bump = None
        if release_bump_value is not None:
            release_bump = _require_string(
                release_bump_value,
                path=f"{workstream_path}.canonical_truth.release_bump",
            )
            if release_bump not in VALID_RELEASE_BUMPS:
                raise ValueError(
                    f"{workstream_path}.canonical_truth.release_bump must be one of {sorted(VALID_RELEASE_BUMPS)}"
                )

        latest_receipts_value = canonical_truth_mapping.get("latest_receipts", {})
        latest_receipts_mapping = _require_mapping(
            latest_receipts_value,
            path=f"{workstream_path}.canonical_truth.latest_receipts",
        )
        latest_receipts: dict[str, str] = {}
        for capability, receipt_id in latest_receipts_mapping.items():
            latest_receipts[
                _require_string(capability, path=f"{workstream_path}.canonical_truth.latest_receipts.key")
            ] = _require_string(
                receipt_id,
                path=f"{workstream_path}.canonical_truth.latest_receipts[{capability}]",
            )

        included_in_repo_version = _require_optional_semver(
            canonical_truth_mapping.get("included_in_repo_version"),
            path=f"{workstream_path}.canonical_truth.included_in_repo_version",
        )

        result.append(
            WorkstreamCanonicalTruth(
                workstream_id=workstream_id,
                adr=adr,
                title=title,
                status=status,
                changelog_entry=changelog_entry,
                release_bump=release_bump,
                included_in_repo_version=included_in_repo_version,
                latest_receipts=latest_receipts,
            )
        )
    return result


def pending_release_workstreams(
    workstreams: list[WorkstreamCanonicalTruth] | None = None,
) -> list[WorkstreamCanonicalTruth]:
    items = workstreams if workstreams is not None else load_workstream_canonical_truth()
    return [
        item
        for item in sorted(items, key=lambda candidate: (int(candidate.adr), candidate.workstream_id))
        if item.status in RELEASE_CANDIDATE_STATUSES
        and item.changelog_entry
        and item.release_bump
        and item.included_in_repo_version is None
    ]


def infer_release_bump(workstreams: list[WorkstreamCanonicalTruth] | None = None) -> str | None:
    ranking = {"patch": 1, "minor": 2, "major": 3}
    pending = pending_release_workstreams(workstreams)
    if not pending:
        return None
    return max((item.release_bump for item in pending if item.release_bump), key=ranking.__getitem__)


def render_unreleased_entries(workstreams: list[WorkstreamCanonicalTruth] | None = None) -> list[str]:
    return [item.changelog_entry for item in pending_release_workstreams(workstreams) if item.changelog_entry]


def assemble_changelog_text(
    changelog_text: str,
    *,
    workstreams: list[WorkstreamCanonicalTruth] | None = None,
) -> str:
    entries = render_unreleased_entries(workstreams)
    match = UNRELEASED_PATTERN.search(changelog_text)
    if not match:
        raise ValueError("changelog.md must contain a '## Unreleased' section before the next heading")

    rendered_body = "\n".join(f"- {entry}" for entry in entries)
    replacement = f"{match.group(1)}\n"
    if rendered_body:
        replacement += f"{rendered_body}\n\n"
    updated = changelog_text[: match.start()] + replacement + changelog_text[match.end() :]
    return updated


def update_stack_repo_version(stack_text: str, version: str) -> str:
    updated, count = re.subn(r"(?m)^repo_version:\s+\S+$", f"repo_version: {version}", stack_text, count=1)
    if count != 1:
        raise ValueError("failed to update versions/stack.yaml repo_version")
    updated, count = re.subn(
        r"(?ms)(^  repo_versioning:\n    current:\s+)\S+",
        rf"\g<1>{version}",
        updated,
        count=1,
    )
    if count != 1:
        raise ValueError("failed to update versions/stack.yaml release_tracks.repo_versioning.current")
    return updated


def assemble_latest_receipts(
    workstreams: list[WorkstreamCanonicalTruth] | None = None,
    *,
    stack_path: Path | None = None,
) -> dict[str, str]:
    resolved_stack_path = stack_path or STACK_PATH
    stack = load_yaml(resolved_stack_path)
    evidence = _require_mapping(stack.get("live_apply_evidence"), path="versions/stack.yaml.live_apply_evidence")
    current_mapping = _require_mapping(
        evidence.get("latest_receipts"),
        path="versions/stack.yaml.live_apply_evidence.latest_receipts",
    )
    assembled = {str(key): str(value) for key, value in current_mapping.items()}
    items = workstreams if workstreams is not None else load_workstream_canonical_truth()
    for item in sorted(
        items,
        key=lambda candidate: (
            parse_semver(candidate.included_in_repo_version) if candidate.included_in_repo_version else (0, 0, 0),
            int(candidate.adr),
            candidate.workstream_id,
        ),
    ):
        if item.status != LIVE_APPLIED_STATUS:
            continue
        for capability, receipt_id in item.latest_receipts.items():
            assembled[capability] = receipt_id
    return assembled


def replace_latest_receipts_block(stack_text: str, latest_receipts: dict[str, str]) -> str:
    match = LATEST_RECEIPTS_PATTERN.search(stack_text)
    if not match:
        raise ValueError("versions/stack.yaml must define live_apply_evidence.latest_receipts")
    rendered_body = "".join(f"    {capability}: {receipt_id}\n" for capability, receipt_id in latest_receipts.items())
    replacement = f"{match.group(1)}{rendered_body}"
    return stack_text[: match.start()] + replacement + stack_text[match.end() :]


def assemble_stack_text(
    stack_text: str,
    *,
    version: str,
    workstreams: list[WorkstreamCanonicalTruth] | None = None,
    stack_path: Path | None = None,
) -> str:
    updated = update_stack_repo_version(stack_text, version)
    latest_receipts = assemble_latest_receipts(workstreams, stack_path=stack_path)
    return replace_latest_receipts_block(updated, latest_receipts)


def render_expected_files() -> dict[Path, str]:
    import generate_status_docs

    workstreams = load_workstream_canonical_truth()
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    expected_changelog = assemble_changelog_text(
        CHANGELOG_PATH.read_text(encoding="utf-8"),
        workstreams=workstreams,
    )
    expected_stack = assemble_stack_text(
        STACK_PATH.read_text(encoding="utf-8"),
        version=version,
        workstreams=workstreams,
    )

    current_stack = STACK_PATH.read_text(encoding="utf-8")
    current_changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
    stack_changed = current_stack != expected_stack
    changelog_changed = current_changelog != expected_changelog

    expected_readme = README_PATH.read_text(encoding="utf-8")
    if not stack_changed and not changelog_changed:
        expected_readme = generate_status_docs.render_readme()

    return {
        CHANGELOG_PATH: expected_changelog,
        STACK_PATH: expected_stack,
        README_PATH: expected_readme,
    }


def write_assembled_truth(*, update_readme: bool = True) -> list[Path]:
    import generate_status_docs

    workstreams = load_workstream_canonical_truth()
    version = VERSION_PATH.read_text(encoding="utf-8").strip()
    changed: list[Path] = []

    assembled_changelog = assemble_changelog_text(
        CHANGELOG_PATH.read_text(encoding="utf-8"),
        workstreams=workstreams,
    )
    if assembled_changelog != CHANGELOG_PATH.read_text(encoding="utf-8"):
        CHANGELOG_PATH.write_text(assembled_changelog, encoding="utf-8")
        changed.append(CHANGELOG_PATH)

    assembled_stack = assemble_stack_text(
        STACK_PATH.read_text(encoding="utf-8"),
        version=version,
        workstreams=workstreams,
    )
    if assembled_stack != STACK_PATH.read_text(encoding="utf-8"):
        STACK_PATH.write_text(assembled_stack, encoding="utf-8")
        changed.append(STACK_PATH)

    if update_readme:
        rendered_readme = generate_status_docs.render_readme()
        current_readme = README_PATH.read_text(encoding="utf-8")
        if rendered_readme != current_readme:
            README_PATH.write_text(rendered_readme, encoding="utf-8")
            changed.append(README_PATH)
    return changed


def check_assembled_truth() -> tuple[int, list[Path]]:
    expected_files = render_expected_files()
    stale_paths = [
        path for path, expected_text in expected_files.items() if expected_text != path.read_text(encoding="utf-8")
    ]
    if stale_paths:
        return 2, stale_paths
    return 0, []


def mark_pending_workstreams_released(version: str, *, workstreams_path: Path | None = None) -> list[str]:
    parse_semver(version)
    resolved_workstreams_path = workstreams_path or WORKSTREAMS_PATH
    items = pending_release_workstreams(load_workstream_canonical_truth(resolved_workstreams_path))
    if not items:
        return []

    if has_sharded_sources(compatibility_path=resolved_workstreams_path):
        changed_ids: list[str] = []
        for item in items:
            record = find_workstream(
                item.workstream_id, compatibility_path=resolved_workstreams_path, include_archive=True
            )
            if record is None or record.location == "compatibility":
                raise ValueError(
                    f"failed to locate shard for workstream '{item.workstream_id}' in {resolved_workstreams_path.name}"
                )
            updated_payload = dict(record.payload)
            canonical_truth = dict(updated_payload.get("canonical_truth") or {})
            canonical_truth["included_in_repo_version"] = version
            updated_payload["canonical_truth"] = canonical_truth
            write_workstream(
                updated_payload,
                compatibility_path=resolved_workstreams_path,
                current_path=record.path,
                archive_year=record.archive_year,
            )
            changed_ids.append(item.workstream_id)
        write_assembled_registry(compatibility_path=resolved_workstreams_path)
        return changed_ids

    updated = resolved_workstreams_path.read_text(encoding="utf-8")
    changed_ids: list[str] = []
    for item in items:
        pattern = re.compile(WORKSTREAM_BLOCK_PATTERN.format(workstream_id=re.escape(item.workstream_id)))
        match = pattern.search(updated)
        if match is None:
            raise ValueError(f"failed to locate workstream '{item.workstream_id}' in {resolved_workstreams_path.name}")

        block = match.group(0)
        if WORKSTREAM_INCLUDED_IN_REPO_VERSION_PATTERN.search(block):
            next_block, count = WORKSTREAM_INCLUDED_IN_REPO_VERSION_PATTERN.subn(
                rf"\g<1>{version}\n",
                block,
                count=1,
            )
        else:
            next_block, count = WORKSTREAM_RELEASE_BUMP_PATTERN.subn(
                rf"\g<1>      included_in_repo_version: {version}\n",
                block,
                count=1,
            )

        if count != 1:
            raise ValueError(
                f"failed to mark workstream '{item.workstream_id}' as released in {resolved_workstreams_path.name}"
            )

        updated = f"{updated[: match.start()]}{next_block}{updated[match.end() :]}"
        changed_ids.append(item.workstream_id)

    resolved_workstreams_path.write_text(updated, encoding="utf-8")
    return changed_ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble integration-only canonical truth files from workstream metadata."
    )
    parser.add_argument("--write", action="store_true", help="Write assembled canonical truth files.")
    parser.add_argument("--check", action="store_true", help="Verify the canonical truth files are current.")
    parser.add_argument(
        "--next-bump",
        action="store_true",
        help="Print the highest pending release bump declared by workstream canonical truth metadata.",
    )
    args = parser.parse_args(argv)

    if sum(bool(flag) for flag in (args.write, args.check, args.next_bump)) != 1:
        parser.print_help()
        return 0

    try:
        if args.next_bump:
            bump = infer_release_bump()
            if bump:
                print(bump)
            return 0
        if args.write:
            changed = write_assembled_truth()
            if changed:
                print("Updated canonical truth:")
                for path in changed:
                    print(f"- {path}")
            else:
                print("Canonical truth already current.")
            return 0
        exit_code, stale_paths = check_assembled_truth()
        if exit_code == 0:
            print("Canonical truth OK")
            return 0
        print(
            "Canonical truth is stale. Run `uvx --from pyyaml python scripts/canonical_truth.py --write`.",
            file=sys.stderr,
        )
        for path in stale_paths:
            print(f"- {path}", file=sys.stderr)
        return exit_code
    except (OSError, RuntimeError, ValueError) as exc:
        return emit_cli_error("Canonical truth", exc)


if __name__ == "__main__":
    sys.exit(main())
