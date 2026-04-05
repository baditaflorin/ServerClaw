#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path(__file__)

from platform.datetime_compat import UTC, datetime
import canonical_truth
import gate_bypass_waivers
from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path, run_command
from generate_release_notes import (
    CHANGELOG_PATH,
    RELEASE_NOTES_INDEX_PATH,
    extract_unreleased_items,
    update_changelog_for_release,
    write_root_summary_documents,
    write_release_artifacts,
)


REPO_ROOT = repo_path()
VERSION_PATH = repo_path("VERSION")
STACK_PATH = repo_path("versions", "stack.yaml")
WORKSTREAMS_PATH = repo_path("workstreams.yaml")
ADR_DIR = repo_path("docs", "adr")
VERSION_SEMANTICS_PATH = repo_path("config", "version-semantics.json")
OUTLINE_SYNC_SCRIPT = repo_path("scripts", "sync_docs_to_outline.py")
OUTLINE_TOOL_SCRIPT = repo_path("scripts", "outline_tool.py")
OUTLINE_API_TOKEN_PATH = repo_path(".local", "outline", "api-token.txt")
OUTLINE_BASE_URL = "https://wiki.lv3.org"
OUTLINE_SYNC_DISABLE_ENV = "LV3_SKIP_OUTLINE_SYNC"
SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class CriterionResult:
    id: str
    label: str
    status: str
    detail: str
    met: bool


def load_version_semantics() -> dict[str, Any]:
    payload = load_json(VERSION_SEMANTICS_PATH)
    if payload.get("schema_version") != "1.0.0":
        raise ValueError("config/version-semantics.json must declare schema_version 1.0.0")
    return payload


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.match(value.strip())
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


def parse_adr_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.startswith("- "):
            if metadata:
                break
            continue
        key, _, value = line[2:].partition(":")
        if value:
            metadata[key.strip()] = value.strip()
    return metadata


def adr_window_result(semantics: dict[str, Any]) -> CriterionResult:
    target = semantics["readiness_targets"]["1.0.0"]["adr_window"]
    start = int(target["start"])
    end = int(target["end"])
    required_statuses = set(target["required_statuses"])
    required_impl = set(target["required_implementation_statuses"])
    implemented = 0
    missing: list[str] = []
    total = end - start + 1
    for adr in range(start, end + 1):
        adr_id = f"{adr:04d}"
        matches = list(ADR_DIR.glob(f"{adr_id}-*.md"))
        if not matches:
            missing.append(adr_id)
            continue
        metadata = parse_adr_metadata(matches[0])
        if metadata.get("Status") in required_statuses and metadata.get("Implementation Status") in required_impl:
            implemented += 1
        else:
            missing.append(adr_id)
    detail = f"{implemented}/{total} implemented"
    if missing:
        detail += f"; first pending: {', '.join(missing[:5])}"
    return CriterionResult(
        id="adr-window",
        label=f"ADR window {start:04d}-{end:04d}",
        status="met" if implemented == total else "pending",
        detail=detail,
        met=implemented == total,
    )


def latest_pass_streak(receipt_dir: Path) -> tuple[int, int]:
    receipts = sorted(receipt_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
    streak = 0
    for receipt in receipts:
        payload = load_json(receipt)
        status = str(payload.get("status") or payload.get("result") or payload.get("outcome") or "").lower()
        if status == "pass":
            streak += 1
            continue
        break
    return streak, len(receipts)


def restore_verification_result(semantics: dict[str, Any]) -> CriterionResult:
    target = semantics["readiness_targets"]["1.0.0"]["restore_verification"]
    receipt_dir = repo_path(target["receipt_dir"])
    required = int(target["required_consecutive_passes"])
    if not receipt_dir.exists():
        return CriterionResult(
            id="restore-verification",
            label="Backup restore verification",
            status="pending",
            detail=f"pending (missing {target['receipt_dir']})",
            met=False,
        )
    streak, total = latest_pass_streak(receipt_dir)
    detail = f"{streak}/{required} consecutive passes from {total} receipt(s)"
    return CriterionResult(
        id="restore-verification",
        label="Backup restore verification",
        status="met" if streak >= required else "pending",
        detail=detail,
        met=streak >= required,
    )


def load_slo_report(report_path: Path) -> dict[str, float]:
    payload = load_json(report_path)
    services = payload.get("services")
    if isinstance(services, list):
        result: dict[str, float] = {}
        for service in services:
            if not isinstance(service, dict):
                continue
            service_id = service.get("service_id")
            remaining = service.get("error_budget_remaining_percent")
            if isinstance(service_id, str) and isinstance(remaining, (int, float)):
                result[service_id] = float(remaining)
        return result
    if isinstance(services, dict):
        result = {}
        for service_id, data in services.items():
            if isinstance(data, dict) and isinstance(data.get("error_budget_remaining_percent"), (int, float)):
                result[str(service_id)] = float(data["error_budget_remaining_percent"])
        return result
    return {}


def slo_result(semantics: dict[str, Any]) -> CriterionResult:
    target = semantics["readiness_targets"]["1.0.0"]
    report_path = repo_path(target["slo_report_path"])
    if not report_path.exists():
        return CriterionResult(
            id="slo-error-budgets",
            label="SLO error budgets",
            status="pending",
            detail=f"pending (missing {target['slo_report_path']})",
            met=False,
        )
    budgets = load_slo_report(report_path)
    missing: list[str] = []
    for requirement in target["required_slos"]:
        service_id = requirement["service_id"]
        minimum = float(requirement["minimum_error_budget_remaining_percent"])
        remaining = budgets.get(service_id)
        if remaining is None or remaining < minimum:
            missing.append(service_id)
    detail = "all required SLOs above threshold" if not missing else f"below target or missing: {', '.join(missing)}"
    return CriterionResult(
        id="slo-error-budgets",
        label="SLO error budgets",
        status="met" if not missing else "pending",
        detail=detail,
        met=not missing,
    )


def probe_url(url: str, timeout: float) -> tuple[bool, str]:
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                code = response.getcode()
            return 200 <= code < 400, f"HTTP {code}"
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code == 405:
                continue
            return False, f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
    return False, "probe failed"


def required_service_results(semantics: dict[str, Any], *, timeout: float) -> list[CriterionResult]:
    results = []
    for service in semantics["readiness_targets"]["1.0.0"]["required_services"]:
        ok, detail = probe_url(service["url"], timeout)
        results.append(
            CriterionResult(
                id=f"service-{service['id']}",
                label=service["label"],
                status="met" if ok else "pending",
                detail=detail if ok else f"pending ({detail})",
                met=ok,
            )
        )
    return results


def dr_table_top_result(semantics: dict[str, Any]) -> CriterionResult:
    receipt_dir = repo_path(semantics["readiness_targets"]["1.0.0"]["dr_table_top_review"]["receipt_dir"])
    receipts = sorted(receipt_dir.glob("*")) if receipt_dir.exists() else []
    if not receipts:
        return CriterionResult(
            id="dr-table-top-review",
            label="DR table-top review",
            status="pending",
            detail=f"pending (missing {receipt_dir.relative_to(REPO_ROOT)})",
            met=False,
        )
    latest = receipts[-1].name
    return CriterionResult(
        id="dr-table-top-review",
        label="DR table-top review",
        status="met",
        detail=f"latest receipt: {latest}",
        met=True,
    )


def release_blockers_result(semantics: dict[str, Any]) -> CriterionResult:
    registry = load_yaml(WORKSTREAMS_PATH)
    blocking_statuses = set(semantics["release_gates"]["blocking_workstream_statuses"])
    blocked = [
        workstream["id"]
        for workstream in registry["workstreams"]
        if workstream.get("status") in blocking_statuses
    ]
    waiver_summary = gate_bypass_waivers.summarize_receipts()
    waiver_blockers = waiver_summary["release_blockers"]
    detail_parts: list[str] = []
    if blocked:
        detail_parts.append(f"{len(blocked)} blocking workstreams: {', '.join(blocked[:5])}")
    else:
        detail_parts.append("0 workstreams in progress")
    if waiver_blockers:
        detail_parts.append(
            "waiver blockers: "
            + ", ".join(
                f"{item['reason_code']} x{item['repeat_after_expiry_occurrences']}"
                for item in waiver_blockers
            )
        )
    return CriterionResult(
        id="release-blockers",
        label="Release blockers",
        status="met" if not blocked and not waiver_blockers else "blocked",
        detail="; ".join(detail_parts),
        met=not blocked and not waiver_blockers,
    )


def build_release_status_snapshot(*, timeout: float = 2.0) -> dict[str, Any]:
    semantics = load_version_semantics()
    stack = load_yaml(STACK_PATH)
    criteria = [
        adr_window_result(semantics),
        slo_result(semantics),
        restore_verification_result(semantics),
        *required_service_results(semantics, timeout=timeout),
        dr_table_top_result(semantics),
    ]
    blockers = release_blockers_result(semantics)
    waiver_summary = gate_bypass_waivers.summarize_receipts()
    met_count = sum(1 for criterion in criteria if criterion.met)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_version": VERSION_PATH.read_text().strip(),
        "platform_version": str(stack["platform_version"]),
        "release_blockers": {
            "status": blockers.status,
            "detail": blockers.detail,
            "met": blockers.met,
        },
        "gate_bypass_waivers": {
            "totals": waiver_summary["totals"],
            "warnings": waiver_summary["warnings"],
            "release_blockers": waiver_summary["release_blockers"],
            "open_waivers": waiver_summary["open_waivers"],
        },
        "target_version": "1.0.0",
        "criteria": [
            {
                "id": criterion.id,
                "label": criterion.label,
                "status": criterion.status,
                "detail": criterion.detail,
                "met": criterion.met,
            }
            for criterion in criteria
        ],
        "summary": {
            "met": met_count,
            "total": len(criteria),
            "percent": round((met_count / len(criteria)) * 100, 2) if criteria else 0.0,
            "ready": blockers.met and met_count == len(criteria),
        },
    }


def render_status(snapshot: dict[str, Any]) -> str:
    waiver_summary = snapshot["gate_bypass_waivers"]
    lines = [
        "Platform 1.0.0 readiness",
        f"- Generated: {snapshot['generated_at']}",
        f"- Repository version: {snapshot['repo_version']}",
        f"- Platform version: {snapshot['platform_version']}",
        f"- Release blockers: {snapshot['release_blockers']['detail']}",
        f"- Gate bypass waivers: {waiver_summary['totals']['open_waivers']} open, {len(waiver_summary['warnings'])} warnings, {len(waiver_summary['release_blockers'])} blockers",
        f"- Criteria met: {snapshot['summary']['met']}/{snapshot['summary']['total']} ({snapshot['summary']['percent']:.2f}%)",
    ]
    for item in waiver_summary["open_waivers"]:
        lines.append(
            f"- OPEN WAIVER {item['reason_code']} until {item['expires_on']} ({item['owner']}; {item['remediation_ref']})"
        )
    for item in waiver_summary["release_blockers"] + waiver_summary["warnings"]:
        lines.append(
            f"- WAIVER {item['status'].upper()} {item['reason_code']}: {item['repeat_after_expiry_occurrences']} repeat(s) past expiry"
        )
    for criterion in snapshot["criteria"]:
        marker = "OK" if criterion["met"] else "PENDING"
        lines.append(f"- {marker} {criterion['label']}: {criterion['detail']}")
    return "\n".join(lines)


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


def default_platform_impact() -> str:
    return "no live platform version bump; this release updates repository automation, release metadata, and operator tooling only"


def _outline_tool_cmd(args: list[str]) -> list[str]:
    return [
        "python3",
        str(OUTLINE_TOOL_SCRIPT),
        *args,
        "--base-url",
        OUTLINE_BASE_URL,
        "--token-file",
        str(OUTLINE_API_TOKEN_PATH),
    ]


def sync_outline_knowledge_surface() -> None:
    if os.environ.get(OUTLINE_SYNC_DISABLE_ENV) == "1":
        return
    if not OUTLINE_SYNC_SCRIPT.exists() or not OUTLINE_API_TOKEN_PATH.exists():
        return
    result = run_command(
        [
            "python3",
            str(OUTLINE_SYNC_SCRIPT),
            "sync",
            "--repo-root",
            str(REPO_ROOT),
            "--base-url",
            OUTLINE_BASE_URL,
            "--api-token-file",
            str(OUTLINE_API_TOKEN_PATH),
        ],
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise ValueError(f"outline knowledge sync failed: {detail}")


def publish_release_to_outline(version: str) -> None:
    """Push the changelog and per-version release notes to the Outline wiki."""
    if os.environ.get(OUTLINE_SYNC_DISABLE_ENV) == "1":
        return
    if not OUTLINE_TOOL_SCRIPT.exists() or not OUTLINE_API_TOKEN_PATH.exists():
        return

    # Push full changelog under a versioned title so history accumulates
    changelog_result = run_command(
        _outline_tool_cmd(["changelog.push", "--title", f"Changelog (as of v{version})"]),
        cwd=REPO_ROOT,
    )
    if changelog_result.returncode != 0:
        detail = (changelog_result.stderr or changelog_result.stdout or "unknown error").strip()
        raise ValueError(f"outline changelog push failed: {detail}")

    # Push the individual release notes file if it exists
    release_notes_path = REPO_ROOT / "docs" / "release-notes" / f"{version}.md"
    if release_notes_path.exists():
        import subprocess
        with open(release_notes_path, encoding="utf-8") as fh:
            content = fh.read()
        proc = subprocess.run(
            _outline_tool_cmd([
                "document.publish",
                "--collection", "Changelogs",
                "--title", f"Release Notes {version}",
                "--rewrite-links",
                "--stdin",
            ]),
            input=content,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "unknown error").strip()
            raise ValueError(f"outline release notes push failed: {detail}")


def refresh_generated_truth_surfaces() -> None:
    commands = [
        (
            "root summary documents",
            [
                "uv",
                "run",
                "--with",
                "pyyaml",
                "python3",
                str(repo_path("scripts", "generate_release_notes.py")),
                "--write-root-summaries",
            ],
        ),
        (
            "generated status docs",
            [
                "uv",
                "run",
                "--with",
                "pyyaml",
                "python3",
                str(repo_path("scripts", "generate_status_docs.py")),
                "--write",
            ],
        ),
        (
            "platform manifest",
            [
                "uv",
                "run",
                "--with",
                "pyyaml",
                "--with",
                "jsonschema",
                "python3",
                str(repo_path("scripts", "platform_manifest.py")),
                "--write",
            ],
        ),
        (
            "generated diagrams",
            [
                "uv",
                "run",
                "--with",
                "pyyaml",
                "python3",
                str(repo_path("scripts", "generate_diagrams.py")),
                "--write",
            ],
        ),
    ]
    for label, command in commands:
        result = run_command(command, cwd=REPO_ROOT)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise ValueError(f"failed to refresh {label}: {detail}")


def write_release(version: str, *, platform_impact: str, released_on: str | None = None) -> dict[str, Any]:
    blockers = release_blockers_result(load_version_semantics())
    if not blockers.met:
        raise ValueError(f"cannot cut a release while blockers remain: {blockers.detail}")
    workstreams = canonical_truth.load_workstream_canonical_truth()
    assembled_changelog = canonical_truth.assemble_changelog_text(
        CHANGELOG_PATH.read_text(),
        workstreams=workstreams,
    )
    notes = extract_unreleased_items(assembled_changelog)
    if not notes:
        raise ValueError("changelog.md has no bullet items under '## Unreleased'")
    VERSION_PATH.write_text(f"{version}\n")
    STACK_PATH.write_text(
        canonical_truth.assemble_stack_text(
            STACK_PATH.read_text(),
            version=version,
            workstreams=workstreams,
        )
    )
    CHANGELOG_PATH.write_text(update_changelog_for_release(assembled_changelog, version, released_on=released_on))
    write_release_artifacts(
        version,
        notes=notes,
        platform_impact=platform_impact,
        released_on=released_on,
    )
    canonical_truth.mark_pending_workstreams_released(version)
    canonical_truth.write_assembled_truth(update_readme=True)
    write_root_summary_documents()
    refresh_generated_truth_surfaces()
    sync_outline_knowledge_surface()
    publish_release_to_outline(version)
    return {"version": version, "notes": notes}


def git_clean() -> bool:
    result = run_command(["git", "status", "--porcelain"], cwd=REPO_ROOT)
    return result.returncode == 0 and not result.stdout.strip()


def tag_exists(tag_name: str) -> bool:
    return run_command(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag_name}"], cwd=REPO_ROOT).returncode == 0


def tag_gpg_sign_enabled() -> bool:
    result = run_command(["git", "config", "--bool", "tag.gpgSign"], cwd=REPO_ROOT)
    return result.returncode == 0 and result.stdout.strip() == "true"


def create_tag(version: str, *, push: bool, dry_run: bool) -> int:
    tag_name = f"v{version}"
    if tag_exists(tag_name):
        raise ValueError(f"git tag already exists: {tag_name}")
    if not git_clean():
        raise ValueError("git worktree must be clean before creating a release tag")
    base_command = ["git", "tag", "-s" if tag_gpg_sign_enabled() else "-a", tag_name, "-m", f"Release {version}"]
    if dry_run:
        print(" ".join(base_command))
        if push:
            print(f"git push origin {tag_name}")
        return 0
    result = subprocess.run(base_command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        return result.returncode
    if push:
        return subprocess.run(["git", "push", "origin", tag_name], cwd=REPO_ROOT, check=False).returncode
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare LV3 repository releases and report product readiness.")
    parser.add_argument("--version", help="Explicit release version to cut.")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], help="Semantic bump to apply to VERSION.")
    parser.add_argument("--platform-impact", default=default_platform_impact(), help="One-line platform impact summary.")
    parser.add_argument("--released-on", help="Release date in YYYY-MM-DD format.")
    parser.add_argument("--dry-run", action="store_true", help="Show the planned release without writing files.")

    subparsers = parser.add_subparsers(dest="action")
    status = subparsers.add_parser("status", help="Show release blockers and product readiness.")
    status.add_argument("--json", action="store_true", help="Emit the readiness snapshot as JSON.")
    status.add_argument("--timeout", type=float, default=2.0, help="Timeout in seconds for URL probes.")

    tag = subparsers.add_parser("tag", help="Create the annotated release tag for the current VERSION.")
    tag.add_argument("--version", help="Version to tag. Defaults to the current VERSION file.")
    tag.add_argument("--push", action="store_true", help="Push the tag to origin after creation.")
    tag.add_argument("--dry-run", action="store_true", help="Print the git commands without running them.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            snapshot = build_release_status_snapshot(timeout=args.timeout)
            if args.json:
                print(json.dumps(snapshot, indent=2))
            else:
                print(render_status(snapshot))
            return 0
        if args.action == "tag":
            version = args.version or VERSION_PATH.read_text().strip()
            return create_tag(version, push=args.push, dry_run=args.dry_run)

        if not args.version and not args.bump:
            args.bump = canonical_truth.infer_release_bump()
        if bool(args.version) == bool(args.bump):
            raise ValueError("choose exactly one of --version or --bump")
        current_version = VERSION_PATH.read_text().strip()
        next_version = args.version or bump_semver(current_version, args.bump)
        if args.dry_run:
            notes = extract_unreleased_items(
                canonical_truth.assemble_changelog_text(
                    CHANGELOG_PATH.read_text(),
                    workstreams=canonical_truth.load_workstream_canonical_truth(),
                )
            )
            print(f"Current version: {current_version}")
            print(f"Next version: {next_version}")
            print(f"Unreleased notes: {len(notes)}")
            print(f"Platform impact: {args.platform_impact}")
            print(f"Release notes index: {RELEASE_NOTES_INDEX_PATH.relative_to(REPO_ROOT)}")
            return 0
        result = write_release(next_version, platform_impact=args.platform_impact, released_on=args.released_on)
        print(f"Prepared release {result['version']} with {len(result['notes'])} changelog note(s).")
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("release manager", exc)


if __name__ == "__main__":
    raise SystemExit(main())
