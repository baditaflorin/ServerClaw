#!/usr/bin/env python3
"""ADR 0488 §4 enforcement — block operator-specific strings in committed files.

The committed code must stay generic-by-default (ADR 0407). Real deployment
identity (apex domain, operator emails, public IPs) lives in `.local/identity.yml`
(gitignored). When operator strings leak into committed files outside a small set
of allowed contexts (ADRs, runbooks, release notes, receipts, build artifacts,
workstreams, RELEASE.md), the private↔public diff balloons and the publish
pipeline has to compensate with brittle regex rewrites.

This script enumerates files tracked by git, scans each one for the blocklist
below (case-insensitive substring match), and exits non-zero on any hit outside
the allowed contexts.

Blocklist:
- `lv3.org`              — retired operator apex
- `0fork.com`            — retired operator apex
- `0mpc.com`             — current operator apex (must stay in .local/)
- `65.109.84.223`        — 0fork host IPv4
- `65.108.75.123`        — lv3 host IPv4
- `2a01:4f9:6b:4b47`     — operator IPv6 prefix

Allowed contexts (substring of the path):
- `docs/adr/`            — historical ADR record
- `docs/release-notes/`  — release-note generator output
- `docs/runbooks/`       — operational procedures (carry real values for the recipe)
- `receipts/`            — live-apply receipts
- `workstreams/`         — workstream registry (informational)
- `build/`               — generated artifacts
- `changelog.md`         — release log
- `RELEASE.md`           — release notes

Usage:
    python3 scripts/audit_sanitization.py            # report and exit non-zero on hits
    python3 scripts/audit_sanitization.py --json     # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BLOCKED_STRINGS: tuple[str, ...] = (
    "lv3.org",
    "0fork.com",
    "0mpc.com",
    "65.109.84.223",
    "65.108.75.123",
    "2a01:4f9:6b:4b47",
)

ALLOWED_PATH_SUBSTRINGS: tuple[str, ...] = (
    "docs/adr/",
    "docs/release-notes/",
    "docs/runbooks/",
    "receipts/",
    "workstreams/",
    "workstreams.yaml",  # generated aggregate of workstreams/active/*.yaml
    "build/",
    "changelog.md",
    "RELEASE.md",
)

# Files this script itself must be exempt from — it names the blocked strings
# in its own source as the blocklist definition.
SELF_EXEMPT: frozenset[str] = frozenset(
    {
        "scripts/audit_sanitization.py",
        "tests/unit/test_audit_sanitization.py",
    }
)


@dataclass(frozen=True)
class Hit:
    path: str
    blocked: str
    line_no: int
    line: str

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "blocked": self.blocked,
            "line_no": self.line_no,
            "line": self.line,
        }


def is_allowed(rel_path: str) -> bool:
    if rel_path in SELF_EXEMPT:
        return True
    return any(token in rel_path for token in ALLOWED_PATH_SUBSTRINGS)


def list_tracked_files(repo_root: Path) -> list[str]:
    """Return paths tracked by git (relative to repo root), one per line."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(repo_root),
        capture_output=True,
        check=True,
    )
    return [p for p in result.stdout.decode("utf-8", errors="replace").split("\0") if p]


def scan_file(path: Path, rel: str, blocked: tuple[str, ...]) -> list[Hit]:
    """Read a tracked file and return any blocked-substring hits.

    Binary files are skipped silently. Decoding falls back to replace so a
    single mojibake byte doesn't mask a leak elsewhere in the file.
    """
    try:
        raw = path.read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return []
    # Heuristic binary skip: NUL byte in first 8 KiB.
    if b"\x00" in raw[:8192]:
        return []
    text = raw.decode("utf-8", errors="replace")
    text_lower = text.lower()
    hits: list[Hit] = []
    for needle in blocked:
        if needle.lower() not in text_lower:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if needle.lower() in line.lower():
                hits.append(Hit(path=rel, blocked=needle, line_no=i, line=line.rstrip()))
    return hits


def audit(
    repo_root: Path,
    blocked: tuple[str, ...] = BLOCKED_STRINGS,
    allowed: tuple[str, ...] = ALLOWED_PATH_SUBSTRINGS,
    files: list[str] | None = None,
) -> list[Hit]:
    """Audit tracked files; return hits in files outside the allowed contexts.

    `files` is for testing — pass an explicit relative-path list to skip the
    `git ls-files` walk. When None, every tracked file in `repo_root` is scanned.
    """

    def _allowed(rel: str) -> bool:
        if rel in SELF_EXEMPT:
            return True
        return any(token in rel for token in allowed)

    if files is None:
        files = list_tracked_files(repo_root)
    hits: list[Hit] = []
    for rel in files:
        if _allowed(rel):
            continue
        hits.extend(scan_file(repo_root / rel, rel, blocked))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="override repo root (for tests / submodules)",
    )
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    hits = audit(root)
    if args.json:
        print(
            json.dumps(
                {"hits": [h.as_dict() for h in hits], "blocked_strings": list(BLOCKED_STRINGS)},
                indent=2,
            )
        )
    else:
        if not hits:
            print(
                f"audit_sanitization: clean — 0 hits across {len(BLOCKED_STRINGS)} "
                "blocked strings (ADR 0488 §4 enforcement)"
            )
        else:
            print(
                f"audit_sanitization: {len(hits)} operator-specific string(s) leaked "
                "into committed files (ADR 0488 §4):\n",
                file=sys.stderr,
            )
            for h in hits:
                print(f"  {h.path}:{h.line_no}  [{h.blocked}]  {h.line}", file=sys.stderr)
            print(
                "\nMove these values to .local/identity.yml or use {{ platform_domain }} / "
                "example.com placeholders. ADR contexts (docs/adr/, docs/runbooks/, "
                "receipts/, etc.) are exempt — see scripts/audit_sanitization.py for the list.",
                file=sys.stderr,
            )
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
