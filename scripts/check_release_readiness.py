#!/usr/bin/env python3
"""Release-readiness checker — validates that the merge-to-main checklist is complete.

Runs as part of CI on PRs targeting main. Checks VERSION bump, changelog entry,
release notes, ADR index, platform manifest, and discovery artifacts.

Usage:
    # Check all release readiness criteria:
    python3 scripts/check_release_readiness.py

    # Check with enforcement (fail on any missing item):
    python3 scripts/check_release_readiness.py --enforce

    # Check against a specific base ref:
    python3 scripts/check_release_readiness.py --base-ref origin/main

    # JSON output for CI parsing:
    python3 scripts/check_release_readiness.py --json

ADR: 0420
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_diff_names(base_ref: str) -> list[str]:
    """Return list of files changed compared to base ref."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip().splitlines() if result.returncode == 0 else []


def _read_version() -> str:
    version_file = REPO_ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return ""


def _release_notes_preserve_changelog_entry(version: str) -> bool:
    """Return true when the current release notes already contain real summary text.

    Canonical release generation clears changelog.md's Unreleased scratchpad after
    cutting docs/release-notes/<VERSION>.md. Accept that released state so this
    checker works both before and after the release artifact generation step.
    """
    if not version:
        return False
    release_notes = REPO_ROOT / "docs" / "release-notes" / f"{version}.md"
    if not release_notes.exists():
        return False

    in_summary = False
    for line in release_notes.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "## Summary":
            in_summary = True
            continue
        if in_summary and stripped.startswith("## "):
            break
        if not in_summary or not stripped.startswith("- "):
            continue
        note = stripped[2:].strip()
        if note and not note.startswith("No changelog notes were present"):
            return True
    return False


def check_version_bumped(changed_files: list[str]) -> dict:
    """Check if VERSION file was changed."""
    bumped = "VERSION" in changed_files
    return {
        "id": "version-bump",
        "passed": bumped,
        "message": "VERSION bumped" if bumped else "VERSION not changed",
        "fix": "Bump VERSION before merging to main (see CLAUDE.md section 4a)",
    }


def check_changelog_entry() -> dict:
    """Check if changelog.md has content under ## Unreleased or release notes."""
    changelog = REPO_ROOT / "changelog.md"
    if not changelog.exists():
        return {
            "id": "changelog-entry",
            "passed": False,
            "message": "changelog.md not found",
            "fix": "Create changelog.md with an ## Unreleased section",
        }

    content = changelog.read_text(encoding="utf-8")
    # Find the Unreleased section and check it has content
    lines = content.splitlines()
    in_unreleased = False
    has_content = False
    for line in lines:
        if line.strip().startswith("## Unreleased"):
            in_unreleased = True
            continue
        if in_unreleased:
            if line.strip().startswith("## "):
                break  # Next section
            if line.strip().startswith("- "):
                has_content = True
                break

    if has_content:
        return {
            "id": "changelog-entry",
            "passed": True,
            "message": "changelog.md has entry under ## Unreleased",
            "fix": "Add a bullet under '## Unreleased' in changelog.md (see CLAUDE.md section 4b)",
        }

    version = _read_version()
    if _release_notes_preserve_changelog_entry(version):
        return {
            "id": "changelog-entry",
            "passed": True,
            "message": f"release notes for {version} preserve the changelog entry",
            "fix": "Add a bullet under '## Unreleased' in changelog.md (see CLAUDE.md section 4b)",
        }

    return {
        "id": "changelog-entry",
        "passed": False,
        "message": "No entry under ## Unreleased in changelog.md",
        "fix": "Add a bullet under '## Unreleased' in changelog.md (see CLAUDE.md section 4b)",
    }


def check_release_notes() -> dict:
    """Check if release notes exist for the current VERSION."""
    version = _read_version()
    if not version:
        return {
            "id": "release-notes",
            "passed": False,
            "message": "Cannot read VERSION",
            "fix": "Ensure VERSION file exists and contains a version string",
        }

    release_notes = REPO_ROOT / "docs" / "release-notes" / f"{version}.md"
    exists = release_notes.exists()
    return {
        "id": "release-notes",
        "passed": exists,
        "message": f"Release notes exist for {version}" if exists else f"No release notes for {version}",
        "fix": f"Run: uv run --with pyyaml python scripts/generate_release_notes.py --version {version} --released-on $(date +%Y-%m-%d) --write",
    }


def check_adr_index() -> dict:
    """Check if ADR index is current (non-stale)."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_adr_index.py"),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    passed = result.returncode == 0
    return {
        "id": "adr-index",
        "passed": passed,
        "message": "ADR index is current" if passed else "ADR index is stale",
        "fix": "Run: python scripts/generate_adr_index.py --write",
    }


def check_platform_manifest() -> dict:
    """Check if platform manifest is current."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "platform_manifest.py"),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    passed = result.returncode == 0
    return {
        "id": "platform-manifest",
        "passed": passed,
        "message": "Platform manifest is current" if passed else "Platform manifest is stale",
        "fix": "Run: uvx --python 3.12 --with pyyaml --with jsonschema --with requests --with jinja2 python scripts/platform_manifest.py --write",
    }


def check_discovery_artifacts() -> dict:
    """Check if discovery artifacts are current."""
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_discovery_artifacts.py"),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    passed = result.returncode == 0
    return {
        "id": "discovery-artifacts",
        "passed": passed,
        "message": "Discovery artifacts are current" if passed else "Discovery artifacts are stale",
        "fix": "Run: python scripts/generate_discovery_artifacts.py --write",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release-readiness checker (ADR 0420)")
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Git ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit with non-zero if any check fails",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    args = parser.parse_args(argv)

    changed_files = _git_diff_names(args.base_ref)

    checks = [
        check_version_bumped(changed_files),
        check_changelog_entry(),
        check_release_notes(),
        check_adr_index(),
        check_platform_manifest(),
        check_discovery_artifacts(),
    ]

    if args.json_output:
        all_passed = all(c["passed"] for c in checks)
        print(
            json.dumps(
                {"passed": all_passed, "checks": checks},
                indent=2,
            )
        )
    else:
        print("\n  Release Readiness (ADR 0420)")
        print("  " + "=" * 50)
        all_passed = True
        for check in checks:
            status = "\033[32m PASS \033[0m" if check["passed"] else "\033[31m FAIL \033[0m"
            print(f"  [{status}] {check['id']}: {check['message']}")
            if not check["passed"]:
                print(f"          Fix: {check['fix']}")
                all_passed = False
        print()
        if all_passed:
            print("  \033[32m All release-readiness checks passed.\033[0m\n")
        else:
            print("  \033[33m Some checks failed — see fix commands above.\033[0m\n")

    if args.enforce and not all(c["passed"] for c in checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
