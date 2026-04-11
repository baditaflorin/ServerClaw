#!/usr/bin/env python3
"""Apply publication-sanitization regex patterns to committed files in-place.

ADR 0407 Phase 4-5: Convert docs/ and tests/ from deployment-specific
values (lv3.org, real hostnames) to generic values (example.com) so the
publish pipeline has fewer files to change.

Usage:
    python3 scripts/generalize_committed_files.py --dry-run   # show what would change
    python3 scripts/generalize_committed_files.py --apply      # apply changes in-place
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "publication-sanitization.yaml"

# Directories to process for generalization
TARGET_DIRS = [
    "docs",
    "tests",
    "config",
    "workstreams",
    "inventory",
]

# Files/dirs to skip
SKIP_DIRS = frozenset({".git", "__pycache__", ".terraform", "node_modules", ".local"})
SKIP_FILES = frozenset(
    {
        # These are managed by Tier A (whole-file replacement) or are the config itself
        "publication-sanitization.yaml",
        "identity.yml",
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


def load_patterns(config_path: Path) -> list[tuple[re.Pattern, str]]:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    patterns = []
    for entry in config.get("string_replacements", []):
        patterns.append((re.compile(entry["pattern"]), entry["replacement"]))
    return patterns


def process_file(fpath: Path, patterns: list[tuple[re.Pattern, str]]) -> tuple[bool, int]:
    """Apply patterns to a single file. Returns (changed, replacement_count)."""
    try:
        content = fpath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False, 0

    original = content
    count = 0
    for pattern, replacement in patterns:
        new_content = pattern.sub(replacement, content)
        if new_content != content:
            count += len(pattern.findall(content))
            content = new_content

    if content != original:
        fpath.write_text(content, encoding="utf-8")
        return True, count
    return False, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generalize committed files (ADR 0407)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show what would change")
    group.add_argument("--apply", action="store_true", help="Apply changes in-place")
    parser.add_argument("--dirs", nargs="+", default=TARGET_DIRS, help="Directories to process")
    args = parser.parse_args()

    patterns = load_patterns(CONFIG_PATH)
    print(f"Loaded {len(patterns)} patterns from {CONFIG_PATH.name}")

    total_files = 0
    changed_files = 0
    total_replacements = 0

    for target_dir in args.dirs:
        dir_path = REPO_ROOT / target_dir
        if not dir_path.is_dir():
            print(f"  SKIP: {target_dir} (not a directory)")
            continue

        for root, dirs, files in os.walk(dir_path):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                if fname in SKIP_FILES:
                    continue
                fpath = root_path / fname
                if fpath.suffix.lower() in BINARY_EXTENSIONS:
                    continue

                total_files += 1

                if args.dry_run:
                    try:
                        content = fpath.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, PermissionError):
                        continue
                    for pattern, replacement in patterns:
                        matches = pattern.findall(content)
                        if matches:
                            rel = fpath.relative_to(REPO_ROOT)
                            print(f"  {rel}: {len(matches)}x {pattern.pattern} → {replacement}")
                            total_replacements += len(matches)
                            content = pattern.sub(replacement, content)
                    if total_replacements > 0:
                        changed_files += 1
                        total_replacements = 0  # reset per-file for counting unique files
                        changed_files_count = changed_files
                else:
                    changed, count = process_file(fpath, patterns)
                    if changed:
                        changed_files += 1
                        total_replacements += count
                        rel = fpath.relative_to(REPO_ROOT)
                        print(f"  {rel}: {count} replacements")

    print(f"\n{'DRY RUN' if args.dry_run else 'APPLIED'}: {changed_files} files changed out of {total_files} scanned")
    if not args.dry_run:
        print(f"Total replacements: {total_replacements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
