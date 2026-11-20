#!/usr/bin/env python3
"""Produce a read-only, evidence-based workstream reconciliation report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

from controller_automation_toolkit import emit_cli_error
from platform.interface_contracts import validate_workstream_repository_references
from platform.repo import load_yaml
from platform.workstream_registry import load_shard_workstreams


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPLETED_TASK_STATUSES = {"complete", "completed", "done"}


def task_summary(workstream: dict[str, Any]) -> tuple[int, int, bool]:
    tasks = workstream.get("tasks")
    if not isinstance(tasks, list):
        return 0, 0, False
    statuses = [str(task.get("status", "")).strip().lower() for task in tasks if isinstance(task, dict)]
    completed = sum(status in COMPLETED_TASK_STATUSES for status in statuses)
    all_completed = bool(tasks) and len(statuses) == len(tasks) and completed == len(tasks)
    return len(tasks), completed, all_completed


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize current workstream evidence without proposing status changes."""
    branch_owners: dict[str, list[str]] = {}
    for workstream in records:
        branch = str(workstream.get("branch", "")).strip()
        if branch:
            branch_owners.setdefault(branch, []).append(str(workstream.get("id", "")))

    entries: list[dict[str, Any]] = []
    for workstream in records:
        status = str(workstream.get("status", ""))
        repositories = workstream.get("repositories")
        repositories = repositories if isinstance(repositories, list) else []
        pull_requests = workstream.get("pull_requests")
        pull_requests = pull_requests if isinstance(pull_requests, list) else []
        task_count, completed_task_count, all_tasks_completed = task_summary(workstream)
        canonical_truth = workstream.get("canonical_truth")
        canonical_truth = canonical_truth if isinstance(canonical_truth, dict) else {}
        included_in_repo_version = canonical_truth.get("included_in_repo_version")
        release_bump = canonical_truth.get("release_bump")
        changelog_entry = canonical_truth.get("changelog_entry")
        release_bookkeeping_pending = bool(
            isinstance(release_bump, str)
            and release_bump.strip()
            and isinstance(changelog_entry, str)
            and changelog_entry.strip()
            and included_in_repo_version is None
        )
        latest_receipts = canonical_truth.get("latest_receipts")
        latest_receipts = latest_receipts if isinstance(latest_receipts, dict) else {}
        reasons: list[str] = []
        if status == "in_progress" and workstream.get("ready_to_merge") is True:
            reasons.append("status_in_progress_but_ready_to_merge")
        if status == "in_progress" and workstream.get("live_applied") is True:
            reasons.append("status_in_progress_but_live_applied_flag")
        if status == "in_progress" and all_tasks_completed:
            reasons.append("all_tasks_marked_completed")
        if status == "in_progress" and included_in_repo_version is not None:
            reasons.append("in_progress_but_included_in_repo_release")
        if status == "in_progress" and not repositories:
            reasons.append("missing_exact_repository_reference")
        if status == "in_progress" and repositories and not pull_requests:
            reasons.append("no_pull_request_reference")
        branch = str(workstream.get("branch", "")).strip()
        duplicate_branches = branch_owners.get(branch, []) if branch else []
        if status == "in_progress" and len(duplicate_branches) > 1:
            reasons.append("branch_name_reused")

        entries.append(
            {
                "id": workstream.get("id", ""),
                "title": workstream.get("title", ""),
                "status": status,
                "location": workstream.get("location", "unknown"),
                "source": workstream.get("source", ""),
                "owner": workstream.get("owner", ""),
                "branch": branch,
                "repositories": sorted({str(repo) for repo in repositories}),
                "pull_requests": pull_requests,
                "ready_to_merge": bool(workstream.get("ready_to_merge", False)),
                "live_applied": bool(workstream.get("live_applied", False)),
                "task_count": task_count,
                "completed_task_count": completed_task_count,
                "all_tasks_completed": all_tasks_completed,
                "release_bookkeeping": {
                    "state": (
                        "pending"
                        if release_bookkeeping_pending
                        else "included"
                        if included_in_repo_version is not None
                        else "not_configured"
                    ),
                    "included_in_repo_version": included_in_repo_version,
                    "release_bump": release_bump,
                    "latest_receipts": latest_receipts,
                },
                "duplicate_branch_workstreams": duplicate_branches if len(duplicate_branches) > 1 else [],
                "review_reasons": reasons,
                "recommendation": "review_evidence_manually" if reasons else "no_flagged_discrepancy",
            }
        )

    in_progress = [entry for entry in entries if entry["status"] == "in_progress"]
    review_entries = [entry for entry in entries if entry["review_reasons"]]
    reason_counts: dict[str, int] = {}
    for entry in entries:
        for reason in entry["review_reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    completion_release_signals = {
        "status_in_progress_but_ready_to_merge",
        "status_in_progress_but_live_applied_flag",
        "all_tasks_marked_completed",
        "in_progress_but_included_in_repo_release",
    }

    return {
        "mode": "read_only",
        "status_changes_made": 0,
        "summary": {
            "workstreams_total": len(entries),
            "workstreams_in_progress": len(in_progress),
            "in_progress_missing_repository_reference": sum(
                "missing_exact_repository_reference" in entry["review_reasons"] for entry in in_progress
            ),
            "in_progress_without_pull_request_reference": sum(
                "no_pull_request_reference" in entry["review_reasons"] for entry in in_progress
            ),
            "in_progress_marked_in_released_version": sum(
                "in_progress_but_included_in_repo_release" in entry["review_reasons"] for entry in in_progress
            ),
            "in_progress_with_completion_or_release_signals": sum(
                bool(completion_release_signals.intersection(entry["review_reasons"])) for entry in in_progress
            ),
            "in_progress_needing_manual_review": sum(bool(entry["review_reasons"]) for entry in in_progress),
            "review_reasons": dict(sorted(reason_counts.items())),
        },
        "entries": entries,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Workstream reconciliation report",
        "",
        "Read-only snapshot. Recommendations identify records to inspect; they do not change status or archive workstreams.",
        "",
        f"- Total records: {summary['workstreams_total']}",
        f"- In progress: {summary['workstreams_in_progress']}",
        f"- In progress without exact repository link: {summary['in_progress_missing_repository_reference']}",
        f"- In progress without PR link: {summary['in_progress_without_pull_request_reference']}",
        f"- In progress needing review: {summary['in_progress_needing_manual_review']}",
        f"- In progress with completion/release signals: {summary['in_progress_with_completion_or_release_signals']}",
        "- Signal counts can overlap: "
        f"ready flag={summary['review_reasons'].get('status_in_progress_but_ready_to_merge', 0)}, "
        f"live-applied flag={summary['review_reasons'].get('status_in_progress_but_live_applied_flag', 0)}, "
        f"all tasks completed={summary['review_reasons'].get('all_tasks_marked_completed', 0)}, "
        f"released version={summary['review_reasons'].get('in_progress_but_included_in_repo_release', 0)}, "
        f"reused branch={summary['review_reasons'].get('branch_name_reused', 0)}",
        "",
        "## Review queue",
        "",
        "| Workstream | Status | Repository | PRs | Release bookkeeping | Evidence to review |",
        "|---|---|---|---|---|---|",
    ]
    for entry in report["entries"]:
        if not entry["review_reasons"]:
            continue
        repo_text = ", ".join(entry["repositories"]) or "unlinked"
        pr_text = (
            ", ".join(f"{pr.get('repository', '?')}#{pr.get('number', '?')}" for pr in entry["pull_requests"])
            or "unlinked"
        )
        reasons = ", ".join(entry["review_reasons"])
        release = entry["release_bookkeeping"]
        release_text = release["state"]
        if release["included_in_repo_version"] is not None:
            release_text += f" ({release['included_in_repo_version']})"
        lines.append(f"| `{entry['id']}` | {entry['status']} | {repo_text} | {pr_text} | {release_text} | {reasons} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A ready flag, live-applied flag, completed checklist, or reused branch name is only a review signal. Confirm the matching repository, merged PR, live-apply receipt, and release bookkeeping before changing a workstream status or archiving it.",
            "",
        ]
    )
    return "\n".join(lines)


def create_report(repo_root: Path, *, include_archive: bool = False) -> dict[str, Any]:
    loaded = load_shard_workstreams(repo_root=repo_root, include_active=True, include_archive=include_archive)
    records = [
        {
            **record.payload,
            "location": record.location,
            "source": str(record.path.relative_to(repo_root)),
        }
        for record in loaded
    ]
    return build_report(records)


def validate_new_workstream_metadata(repo_root: Path, base_ref: str) -> list[str]:
    """Require exact repo/PR fields on active shards changed from the base ref."""
    changed_files_json = os.environ.get("LV3_VALIDATION_CHANGED_FILES_JSON", "").strip()
    if changed_files_json:
        changed_files = json.loads(changed_files_json)
        if not isinstance(changed_files, list) or any(not isinstance(item, str) for item in changed_files):
            raise ValueError("LV3_VALIDATION_CHANGED_FILES_JSON must be an array of path strings")
        candidate_paths = {item.strip().replace("\\", "/") for item in changed_files if item.strip()}
    else:
        changed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--name-only",
                "--diff-filter=AM",
                base_ref,
                "--",
                "workstreams/active",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        untracked = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard", "--", "workstreams/active"],
            check=True,
            capture_output=True,
            text=True,
        )
        candidate_paths = set(changed.stdout.splitlines()) | set(untracked.stdout.splitlines())
    failures: list[str] = []
    changed_paths = sorted(path for path in candidate_paths if path.startswith("workstreams/active/"))
    for raw_path in changed_paths:
        path = repo_root / raw_path
        if path.suffix not in {".yaml", ".yml"} or not path.is_file():
            continue
        workstream = load_yaml(path)
        if not isinstance(workstream, dict):
            failures.append(f"{raw_path}: workstream shard must be a mapping")
            continue
        missing = [field for field in ("repositories", "pull_requests") if field not in workstream]
        if missing:
            failures.append(f"{raw_path}: add explicit {', '.join(missing)} metadata (use [] for no PRs yet)")
            continue
        try:
            validate_workstream_repository_references(workstream, raw_path)
        except ValueError as exc:
            failures.append(f"{raw_path}: {exc}")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--include-archive", action="store_true", help="Include archived workstreams.")
    parser.add_argument(
        "--check-new-metadata", action="store_true", help="Validate exact references on changed active shards"
    )
    parser.add_argument("--base-ref", default="origin/main", help="Git base ref for --check-new-metadata")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check_new_metadata:
            failures = validate_new_workstream_metadata(args.repo_root, args.base_ref)
            if failures:
                print("New or changed active workstreams need repository/PR metadata:", file=sys.stderr)
                for failure in failures:
                    print(f"- {failure}", file=sys.stderr)
                return 1
            print(f"Changed active workstream metadata is valid against {args.base_ref}.")
            return 0
        report = create_report(args.repo_root, include_archive=args.include_archive)
        print(json.dumps(report, indent=2) if args.format == "json" else render_markdown(report))
        return 0
    except (FileNotFoundError, OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        return emit_cli_error("workstream reconciliation", exc)


if __name__ == "__main__":
    raise SystemExit(main())
