#!/usr/bin/env python3
"""ADR 0408: Rename -lv3 inventory hostnames to generic names.

One-time migration script. Performs literal string replacement across
all tracked files, ordered from longest to shortest to prevent partial matches.

Usage:
    python3 scripts/one-time/adr-0408-rename-inventory-hostnames.py --dry-run
    python3 scripts/one-time/adr-0408-rename-inventory-hostnames.py --apply
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Ordered from longest to shortest to prevent partial matches.
# Each tuple: (old_name, new_name)
RENAMES: list[tuple[str, str]] = [
    # Staging (longer, must come first)
    ("docker-runtime-staging-lv3", "docker-runtime-staging"),
    ("artifact-cache-staging-lv3", "artifact-cache-staging"),
    ("docker-build-staging-lv3", "docker-build-staging"),
    ("monitoring-staging-lv3", "monitoring-staging"),
    ("postgres-staging-lv3", "postgres-staging"),
    ("backup-staging-lv3", "backup-staging"),
    ("nginx-staging-lv3", "nginx-staging"),
    # Production (longer compound names first)
    ("postgres-replica-lv3", "postgres-replica"),
    ("runtime-control-lv3", "runtime-control"),
    ("runtime-general-lv3", "runtime-general"),
    ("docker-runtime-lv3", "docker-runtime"),
    ("artifact-cache-lv3", "artifact-cache"),
    ("coolify-apps-lv3", "coolify-apps"),
    ("runtime-comms-lv3", "runtime-comms"),
    ("runtime-apps-lv3", "runtime-apps"),
    ("postgres-apps-lv3", "postgres-apps"),
    ("postgres-data-lv3", "postgres-data"),
    ("docker-build-lv3", "docker-build"),
    ("postgres-vm-lv3", "postgres-vm"),
    ("monitoring-lv3", "monitoring"),
    ("runtime-ai-lv3", "runtime-ai"),
    ("coolify-lv3", "coolify"),
    ("postgres-lv3", "postgres"),
    ("backup-lv3", "backup"),
    ("nginx-lv3", "nginx"),
]

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".db",
    ".sqlite",
    ".sqlite3",
}

SKIP_PREFIXES = [".local/", "publication/", ".git/"]


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return [f for f in result.stdout.strip().split("\n") if f]


def apply_renames(content: str) -> str:
    for old, new in RENAMES:
        content = content.replace(old, new)
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR 0408: Rename inventory hostnames")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show what would change")
    group.add_argument("--apply", action="store_true", help="Apply changes in-place")
    args = parser.parse_args()

    files = tracked_files()
    changed_files: list[str] = []
    total_replacements = 0

    for rel_path in files:
        if any(rel_path.startswith(p) for p in SKIP_PREFIXES):
            continue

        fpath = REPO_ROOT / rel_path
        if fpath.suffix.lower() in BINARY_EXTENSIONS:
            continue
        if not fpath.is_file():
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        new_content = apply_renames(content)
        if new_content != content:
            # Count replacements
            count = 0
            for old, new in RENAMES:
                count += content.count(old)
            total_replacements += count
            changed_files.append(rel_path)

            if args.apply:
                fpath.write_text(new_content, encoding="utf-8")

            if args.dry_run:
                # Show first few replacements per file
                for old, new in RENAMES:
                    c = content.count(old)
                    if c > 0:
                        print(f"  {rel_path}: {old} -> {new} ({c}x)")

    print(
        f"\n{'Would change' if args.dry_run else 'Changed'}: {len(changed_files)} files, {total_replacements} replacements"
    )

    if args.apply:
        # Rename host_vars file
        old_hv = REPO_ROOT / "inventory" / "host_vars" / "runtime-control-lv3.yml"
        new_hv = REPO_ROOT / "inventory" / "host_vars" / "runtime-control.yml"
        if old_hv.exists() and not new_hv.exists():
            subprocess.run(["git", "mv", str(old_hv), str(new_hv)], cwd=REPO_ROOT)
            print(f"Renamed: {old_hv.name} -> {new_hv.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
