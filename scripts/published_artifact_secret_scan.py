#!/usr/bin/env python3
"""Scan published repository artifacts for secrets before release or publication."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / ".gitleaks.toml"
DEFAULT_PATTERNS = (
    "receipts/**/*.json",
    ".local/triage/reports/**/*.json",
    "build/search-index/**/*.json",
    "build/changelog-portal/**/*.html",
    "build/changelog-portal/**/*.json",
)


@dataclass(frozen=True)
class ScanFinding:
    rule_id: str
    description: str
    path: str
    line: int


@dataclass(frozen=True)
class ScanResult:
    mode: str
    scanned_files: int
    findings: list[ScanFinding]

    @property
    def file_count_with_findings(self) -> int:
        return len({finding.path for finding in self.findings})


@dataclass(frozen=True)
class BuiltinRule:
    rule_id: str
    description: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class BuiltinAllowlist:
    path_patterns: tuple[re.Pattern[str], ...]
    match_patterns: tuple[re.Pattern[str], ...]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan published repository artifacts for secrets.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root to scan.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the gitleaks configuration file.",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Specific path relative to the repo root to scan. Repeat for multiple paths.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Additional glob pattern relative to the repo root to scan. Repeat for multiple patterns.",
    )
    parser.add_argument(
        "--gitleaks-binary",
        default="gitleaks",
        help="Binary to use for gitleaks execution. Defaults to 'gitleaks'.",
    )
    parser.add_argument(
        "--enforce-gitleaks",
        action="store_true",
        help="Fail if the configured gitleaks binary is unavailable instead of falling back to builtin rule scanning.",
    )
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Emit the scan result as JSON after the human-readable summary.",
    )
    return parser.parse_args(argv)


def load_builtin_config(config_path: Path) -> tuple[list[BuiltinRule], BuiltinAllowlist]:
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    rules = [
        BuiltinRule(
            rule_id=str(rule["id"]),
            description=str(rule.get("description") or rule["id"]),
            pattern=re.compile(str(rule["regex"]), re.MULTILINE),
        )
        for rule in payload.get("rules", [])
        if isinstance(rule, dict) and rule.get("id") and rule.get("regex")
    ]
    allowlist_payload = payload.get("allowlist") or {}
    allowlist = BuiltinAllowlist(
        path_patterns=tuple(
            re.compile(str(pattern))
            for pattern in allowlist_payload.get("paths", [])
            if isinstance(pattern, str) and pattern
        ),
        match_patterns=tuple(
            re.compile(str(pattern))
            for pattern in allowlist_payload.get("regexes", [])
            if isinstance(pattern, str) and pattern
        ),
    )
    return rules, allowlist


def iter_candidate_files(repo_root: Path, *, paths: list[str], patterns: list[str]) -> list[Path]:
    discovered: set[Path] = set()

    for relative in paths:
        candidate = (repo_root / relative).resolve()
        if not candidate.exists():
            continue
        if candidate.is_dir():
            for path in sorted(candidate.rglob("*")):
                if path.is_file():
                    discovered.add(path)
        elif candidate.is_file():
            discovered.add(candidate)

    glob_patterns = patterns or list(DEFAULT_PATTERNS)
    for pattern in glob_patterns:
        for path in sorted(repo_root.glob(pattern)):
            if path.is_file():
                discovered.add(path.resolve())

    return sorted(discovered)


def is_allowlisted(relative_path: str, matched_text: str, allowlist: BuiltinAllowlist) -> bool:
    if any(pattern.search(relative_path) for pattern in allowlist.path_patterns):
        return True
    return any(pattern.search(matched_text) for pattern in allowlist.match_patterns)


def scan_with_builtin_rules(
    repo_root: Path,
    files: list[Path],
    *,
    config_path: Path,
) -> ScanResult:
    rules, allowlist = load_builtin_config(config_path)
    findings: list[ScanFinding] = []

    for path in files:
        relative_path = path.resolve().relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "\x00" in text:
            continue
        for rule in rules:
            for match in rule.pattern.finditer(text):
                matched_text = match.group(0)
                if is_allowlisted(relative_path, matched_text, allowlist):
                    continue
                findings.append(
                    ScanFinding(
                        rule_id=rule.rule_id,
                        description=rule.description,
                        path=relative_path,
                        line=text.count("\n", 0, match.start()) + 1,
                    )
                )

    return ScanResult(mode="builtin", scanned_files=len(files), findings=findings)


def stage_files(repo_root: Path, files: list[Path], staging_root: Path) -> None:
    for path in files:
        relative_path = path.resolve().relative_to(repo_root)
        destination = staging_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def normalize_gitleaks_path(file_path: str, staging_root: Path) -> str:
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = (staging_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        return candidate.relative_to(staging_root.resolve()).as_posix()
    except ValueError:
        return file_path


def scan_with_gitleaks(
    repo_root: Path,
    files: list[Path],
    *,
    config_path: Path,
    gitleaks_binary: str,
) -> ScanResult:
    with tempfile.TemporaryDirectory(prefix="lv3-published-artifacts-") as temp_dir:
        staging_root = Path(temp_dir)
        report_path = staging_root / "gitleaks-report.json"
        stage_files(repo_root, files, staging_root)
        command = [
            gitleaks_binary,
            "detect",
            "--config",
            str(config_path),
            "--no-git",
            "--source",
            str(staging_root),
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode not in {0, 1}:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown gitleaks error"
            raise RuntimeError(f"gitleaks execution failed: {detail}")
        payload = []
        if report_path.exists():
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        findings = [
            ScanFinding(
                rule_id=str(item.get("RuleID") or item.get("rule_id") or "unknown-rule"),
                description=str(item.get("Description") or item.get("description") or "gitleaks finding"),
                path=normalize_gitleaks_path(str(item.get("File") or item.get("file") or ""), staging_root),
                line=int(item.get("StartLine") or item.get("start_line") or 1),
            )
            for item in payload
            if isinstance(item, dict)
        ]
        return ScanResult(mode="gitleaks", scanned_files=len(files), findings=findings)


def gitleaks_available(gitleaks_binary: str) -> bool:
    if Path(gitleaks_binary).expanduser().exists():
        return True
    return shutil.which(gitleaks_binary) is not None


def scan_published_artifacts(
    repo_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    paths: list[str] | None = None,
    patterns: list[str] | None = None,
    gitleaks_binary: str = "gitleaks",
    enforce_gitleaks: bool = False,
) -> ScanResult:
    resolved_repo_root = repo_root.resolve()
    files = iter_candidate_files(resolved_repo_root, paths=paths or [], patterns=patterns or [])
    if gitleaks_available(gitleaks_binary):
        return scan_with_gitleaks(
            resolved_repo_root,
            files,
            config_path=config_path.resolve(),
            gitleaks_binary=gitleaks_binary,
        )
    if enforce_gitleaks:
        raise RuntimeError(f"gitleaks binary '{gitleaks_binary}' is not available")
    return scan_with_builtin_rules(
        resolved_repo_root,
        files,
        config_path=config_path.resolve(),
    )


def print_summary(result: ScanResult) -> None:
    if not result.findings:
        print(
            f"Published artifact secret scan passed: {result.scanned_files} file(s) checked with {result.mode}."
        )
        return
    print(
        "Published artifact secret scan failed: "
        f"{len(result.findings)} finding(s) across {result.file_count_with_findings} file(s) "
        f"checked with {result.mode}."
    )
    for finding in result.findings:
        print(f"- {finding.path}:{finding.line} [{finding.rule_id}] {finding.description}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = scan_published_artifacts(
        args.repo_root,
        config_path=args.config,
        paths=args.path,
        patterns=args.pattern,
        gitleaks_binary=args.gitleaks_binary,
        enforce_gitleaks=args.enforce_gitleaks,
    )
    print_summary(result)
    if args.print_json:
        print(
            json.dumps(
                {
                    "mode": result.mode,
                    "scanned_files": result.scanned_files,
                    "findings": [asdict(finding) for finding in result.findings],
                },
                indent=2,
            )
        )
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
