#!/usr/bin/env python3
"""
Pre-commit hook to prevent srvclaw_ prefixed secrets from being committed (ADR 0480).

All real secrets now use srvclaw_<service>_<random> format for easy identification.
This hook prevents any srvclaw_ pattern from being committed to git.

Returns 0 if no srvclaw_ patterns found, 1 if secrets found in commits.
"""

import re
import subprocess
import sys


def get_staged_files():
    """Get list of staged files in the current commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def get_staged_content(file_path):
    """Get the staged content of a file."""
    result = subprocess.run(
        ["git", "show", f":{file_path}"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def is_allowed_file(file_path):
    """Check if file is excluded from secret scanning."""
    excluded_patterns = [
        r"^\.local/",  # gitignored anyway
        r"^docs/adr/",  # ADR files can contain example secrets
        r"^docs/postmortems/",  # docs can reference real/masked versions
        r"^build/changelog-portal/",  # generated artifacts
        r"^CHANGELOG\.md$",  # release notes
        r"^changelog\.md$",
    ]

    for pattern in excluded_patterns:
        if re.match(pattern, file_path):
            return True
    return False


def find_srvclaw_secrets(content, file_path):
    """Find srvclaw_ patterns that shouldn't be in commits."""
    violations = []

    # Skip if file is allowed
    if is_allowed_file(file_path):
        return violations

    lines = content.split("\n")

    for line_num, line in enumerate(lines, 1):
        # Skip comments and documentation strings
        if line.strip().startswith("#") or line.strip().startswith("//"):
            continue

        # Look for srvclaw_ pattern (the actual secret format)
        matches = re.finditer(r"srvclaw_[a-z0-9_]+_[A-Za-z0-9_\-]{20,}", line)
        for match in matches:
            secret = match.group(0)
            violations.append(
                {
                    "file": file_path,
                    "line": line_num,
                    "secret": secret[:40] + ("..." if len(secret) > 40 else ""),
                    "raw_line": line.strip()[:100],
                }
            )

    return violations


def main():
    staged_files = get_staged_files()
    if not staged_files:
        return 0

    all_violations = []

    for file_path in staged_files:
        if not file_path or file_path.startswith("."):
            continue

        try:
            content = get_staged_content(file_path)
            violations = find_srvclaw_secrets(content, file_path)
            all_violations.extend(violations)
        except Exception:
            # Skip files that can't be read (deleted, etc.)
            pass

    if all_violations:
        print("🔒 Pre-commit: srvclaw_ secrets detected in commit", file=sys.stderr)
        print("\n❌ Real secrets found in staged files (should only be in .local/):\n", file=sys.stderr)
        for v in all_violations[:10]:
            print(
                f"  {v['file']}:{v['line']} — {v['secret']}",
                file=sys.stderr,
            )
        print(
            "\n✓ Fix: Move files with srvclaw_* secrets to .local/ or .gitignore",
            file=sys.stderr,
        )
        print("  Real passwords should NEVER be committed to git.\n", file=sys.stderr)
        return 1

    print("✓ Secret filter passed: no srvclaw_ patterns in commit", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
