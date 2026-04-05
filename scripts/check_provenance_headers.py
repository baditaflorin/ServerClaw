#!/usr/bin/env python3
"""ADR 0351: Audit Jinja2 templates for missing provenance headers.

Scans all *.j2 templates in roles/*/templates/ and reports which ones
are missing a 'managed-by:' provenance comment.

Usage:
    python scripts/check_provenance_headers.py [--repo-root PATH] [--strict]

Output:
    Lists templates missing headers.
    With --strict, exits non-zero if any are missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROVENANCE_MARKER = "managed-by:"
SKIP_PATTERNS = {"lv3_provenance_header.j2"}  # the macro itself


def check_template(path: Path) -> bool:
    """Return True if template has a provenance header."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return PROVENANCE_MARKER in content
    except OSError:
        return False


def find_templates(roles_dir: Path) -> list[Path]:
    return sorted(
        p for p in roles_dir.glob("*/templates/*.j2")
        if p.name not in SKIP_PATTERNS
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ADR 0351 provenance headers")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any headers missing")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    roles_dir = repo_root / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"

    if not roles_dir.is_dir():
        print(f"ERROR: {roles_dir} not found", file=sys.stderr)
        return 1

    templates = find_templates(roles_dir)
    missing = [t for t in templates if not check_template(t)]
    tagged = len(templates) - len(missing)

    print(f"Provenance header audit: {tagged}/{len(templates)} templates tagged")
    if missing:
        print(f"\nMissing ({len(missing)}):")
        for t in missing:
            # Print relative path for readability
            try:
                rel = t.relative_to(repo_root)
            except ValueError:
                rel = t
            print(f"  {rel}")

    return 1 if (args.strict and missing) else 0


if __name__ == "__main__":
    sys.exit(main())
