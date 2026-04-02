#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ENTRYPOINTS = [
    Path("README.md"),
    Path("AGENTS.md"),
    Path(".repo-structure.yaml"),
    Path(".config-locations.yaml"),
    Path("workstreams.yaml"),
    Path("changelog.md"),
    Path("docs/release-notes/README.md"),
]
PUBLIC_GENERIC_ENTRYPOINTS = [
    Path("README.md"),
    Path("AGENTS.md"),
    Path(".repo-structure.yaml"),
]
PERSONAL_PATH_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"/Users/[^/\s]+/"), "macOS home path"),
    (re.compile(r"/home/[^/\s]+/"), "Linux home path"),
    (re.compile(r"[A-Za-z]:\\\\Users\\\\"), "Windows home path"),
]
DEPLOYMENT_SPECIFIC_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bHetzner\b"), "provider-specific reference"),
    (re.compile(r"\bproxmox_florin\b"), "deployment-specific hostname label"),
    (re.compile(r"\blv3\.org\b"), "deployment-specific domain"),
    (re.compile(r"\b65\.108\.75\.123\b"), "deployment-specific public IPv4"),
    (re.compile(r"\b100\.64\.0\.1\b"), "deployment-specific mesh address"),
    (re.compile(r"\b10\.10\.10\."), "deployment-specific guest subnet"),
]


def _iter_pattern_hits(
    text: str,
    patterns: Iterable[tuple[re.Pattern[str], str]],
) -> list[str]:
    findings: list[str] = []
    for pattern, label in patterns:
        for match in pattern.finditer(text):
            findings.append(f"{label}: {match.group(0)}")
    return findings


def _is_absolute_path(value: str) -> bool:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        return False
    if normalized.startswith("/"):
        return True
    return bool(re.match(r"^[A-Za-z]:/", normalized))


def _validate_text_surfaces() -> list[str]:
    findings: list[str] = []
    for relative_path in PUBLIC_ENTRYPOINTS:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        for hit in _iter_pattern_hits(text, PERSONAL_PATH_PATTERNS):
            findings.append(f"{relative_path}: {hit}")
        if relative_path in PUBLIC_GENERIC_ENTRYPOINTS:
            for hit in _iter_pattern_hits(text, DEPLOYMENT_SPECIFIC_PATTERNS):
                findings.append(f"{relative_path}: {hit}")
    return findings


def _validate_workstream_registry() -> list[str]:
    findings: list[str] = []
    payload = yaml.safe_load((REPO_ROOT / "workstreams.yaml").read_text(encoding="utf-8")) or {}

    delivery_model = payload.get("delivery_model", {}) or {}
    workstream_doc_root = str(delivery_model.get("workstream_doc_root", "")).strip()
    if workstream_doc_root and _is_absolute_path(workstream_doc_root):
        findings.append(
            "workstreams.yaml: delivery_model.workstream_doc_root must be repository-relative"
        )

    release_policy = payload.get("release_policy", {}) or {}
    breaking_change_criteria = str(release_policy.get("breaking_change_criteria", "")).strip()
    if breaking_change_criteria and _is_absolute_path(breaking_change_criteria):
        findings.append(
            "workstreams.yaml: release_policy.breaking_change_criteria must be repository-relative"
        )

    for index, workstream in enumerate(payload.get("workstreams", []) or []):
        if not isinstance(workstream, dict):
            continue
        worktree_path = str(workstream.get("worktree_path", "")).strip()
        if worktree_path and _is_absolute_path(worktree_path):
            findings.append(
                f"workstreams.yaml: workstreams[{index}].worktree_path must be repository-relative"
            )
        doc = str(workstream.get("doc", "")).strip()
        if doc and _is_absolute_path(doc):
            findings.append(
                f"workstreams.yaml: workstreams[{index}].doc must be repository-relative"
            )

    return findings


def validate_public_entrypoints() -> list[str]:
    return [*_validate_text_surfaces(), *_validate_workstream_registry()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate public entrypoints stay generic and machine-portable."
    )
    parser.add_argument("--check", action="store_true", help="Validate and exit non-zero on findings.")
    args = parser.parse_args(argv)

    findings = validate_public_entrypoints()
    if findings:
        if args.check:
            print("Public entrypoint validation failed:", file=sys.stderr)
            for finding in findings:
                print(f"- {finding}", file=sys.stderr)
            return 1
        for finding in findings:
            print(finding)
        return 0

    if args.check:
        print("Public entrypoints OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
