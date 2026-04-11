#!/usr/bin/env python3
"""ADR 0409 — Generalize all committed code to eliminate publication sanitization.

Applies the SAME string replacements the publication pipeline uses, but to
the committed source files instead of a temporary worktree copy.

After this script runs, the committed code should contain zero leak-marker
matches and require zero Tier C regex replacements during publication.

Usage:
    python3 scripts/one-time/adr-0409-generalize-committed-code.py --dry-run
    python3 scripts/one-time/adr-0409-generalize-committed-code.py --apply
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --------------------------------------------------------------------------
# Replacement patterns — ordered longest/most-specific first.
# This is the SAME list as config/publication-sanitization.yaml string_replacements.
# --------------------------------------------------------------------------
REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    # Repo checkout path (must come before proxmox_florin)
    (re.compile(r"proxmox_florin_server"), "platform_server"),
    # PII — longer names first
    (re.compile(r"Florin Badita-Nistor"), "Platform Operator"),
    (re.compile(r"Florin Badita"), "Platform Operator"),
    # PII — emails (specific before domain-general)
    (re.compile(r"busui\.matei1994@gmail\.com"), "operator@example.com"),
    (re.compile(r"baditaflorin\+tmp\d+@gmail\.com"), "operator@example.com"),
    (re.compile(r"baditaflorin@gmail\.com"), "operator@example.com"),
    (re.compile(r"florin@badita\.org"), "operator@example.com"),
    (re.compile(r"florin@lv3\.org"), "operator@example.com"),
    # Domain (must come before shorter patterns)
    (re.compile(r"lv3\.org"), "example.com"),
    # VM/host names
    (re.compile(r"proxmox_florin"), "proxmox-host"),
    (re.compile(r"proxmox-florin"), "proxmox-host"),
    (re.compile(r"Debian-trixie-latest-amd64-base"), "debian-base-template"),
    # Real public IPs → RFC 5737 documentation IPs
    (re.compile(r"65\.108\.75\.123"), "203.0.113.1"),
    (re.compile(r"65\.108\.75\.65"), "203.0.113.65"),
    (re.compile(r"65\.108\.75\.64"), "203.0.113.0"),
    # IPv6 → RFC 3849 documentation prefix
    (re.compile(r"2a01:4f9:6b:4b47::2"), "2001:db8::2"),
    (re.compile(r"2a01:4f8:d0a:27bd::2"), "2001:db8::3"),
    # Management ACL IP
    (re.compile(r"90\.95\.35\.115"), "203.0.113.100"),
]

# Files/directories to skip
SKIP_DIRS = frozenset(
    {
        ".git",
        ".local",
        "__pycache__",
        ".terraform",
        "node_modules",
        "publication",  # Publication templates stay as-is
    }
)

SKIP_FILES = frozenset(
    {
        # The migration script itself
        "adr-0409-generalize-committed-code.py",
        # Publication sanitization config (stays deployment-aware)
        "publication-sanitization.yaml",
        # Audit script references real values as expected-values
        "audit_sanitization_coverage.py",
    }
)

BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".pdf",
        ".pyc",
        ".pyo",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)


def get_committed_files() -> list[Path]:
    """Get all files tracked by git."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return [REPO_ROOT / f for f in result.stdout.split("\0") if f]


def should_skip(path: Path) -> bool:
    """Check if a file should be skipped."""
    rel = path.relative_to(REPO_ROOT)
    parts = rel.parts

    # Skip directories
    if any(part in SKIP_DIRS for part in parts):
        return True

    # Skip specific files
    if rel.name in SKIP_FILES:
        return True

    # Skip binary files
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    return False


def apply_replacements(content: str) -> tuple[str, list[str]]:
    """Apply all replacements to content. Returns (new_content, list_of_changes)."""
    changes = []
    for pattern, replacement in REPLACEMENTS:
        matches = pattern.findall(content)
        if matches:
            changes.append(f"  {pattern.pattern} → {replacement} ({len(matches)} occurrences)")
            content = pattern.sub(replacement, content)
    return content, changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Generalize committed code (ADR 0409)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show what would change")
    group.add_argument("--apply", action="store_true", help="Apply changes")
    args = parser.parse_args()

    files = get_committed_files()
    total_files_changed = 0
    total_replacements = 0

    for fpath in sorted(files):
        if should_skip(fpath):
            continue

        if not fpath.exists() or not fpath.is_file():
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        new_content, changes = apply_replacements(content)

        if changes:
            total_files_changed += 1
            rel = fpath.relative_to(REPO_ROOT)
            replacement_count = sum(int(c.split("(")[1].split(" ")[0]) for c in changes)
            total_replacements += replacement_count

            if args.dry_run:
                print(f"\n{rel} ({replacement_count} replacements):")
                for change in changes:
                    print(change)
            else:
                fpath.write_text(new_content, encoding="utf-8")
                print(f"  updated: {rel} ({replacement_count} replacements)")

    print(
        f"\n{'Would modify' if args.dry_run else 'Modified'}: {total_files_changed} files, {total_replacements} total replacements"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
