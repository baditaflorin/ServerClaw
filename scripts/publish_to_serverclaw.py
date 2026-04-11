#!/usr/bin/env python3
"""Sanitize the private repo and push to the public ServerClaw repo.

Usage:
    python3 scripts/publish_to_serverclaw.py              # dry-run (sanitize + leak check, no push)
    python3 scripts/publish_to_serverclaw.py --push        # sanitize + push to serverclaw remote
    python3 scripts/publish_to_serverclaw.py --diff        # show what would change vs current serverclaw/main
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "publication-sanitization.yaml"
REMOTE_NAME = "serverclaw"

# Binary file extensions to skip during regex replacement
BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".otf", ".zip", ".tar", ".gz", ".bz2", ".xz",
    ".pdf", ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".db", ".sqlite", ".sqlite3",
})

# Directories to always skip
SKIP_DIRS = frozenset({".git", "__pycache__", ".terraform", "node_modules"})


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def create_worktree(source_ref: str = "HEAD") -> Path:
    """Create a temporary git worktree for sanitization."""
    tmpdir = Path(tempfile.mkdtemp(prefix="serverclaw-publish-"))
    worktree_path = tmpdir / "publish"
    run(
        ["git", "worktree", "add", "--detach", str(worktree_path), source_ref],
        cwd=REPO_ROOT,
    )
    return worktree_path


def remove_worktree(worktree_path: Path) -> None:
    """Remove the temporary worktree."""
    try:
        run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=REPO_ROOT)
    except subprocess.CalledProcessError:
        pass
    parent = worktree_path.parent
    if parent.exists():
        shutil.rmtree(parent, ignore_errors=True)


def apply_file_replacements(worktree: Path, config: dict) -> int:
    """Replace entire files with their template versions (Tier A)."""
    count = 0
    for entry in config.get("file_replacements", []):
        src = REPO_ROOT / entry["template"]
        dst = worktree / entry["source"]
        if src.exists():
            shutil.copy2(src, dst)
            count += 1
            print(f"  replaced: {entry['source']}")
        else:
            print(f"  WARNING: template missing: {src}", file=sys.stderr)
    return count


def apply_string_replacements(worktree: Path, config: dict) -> int:
    """Apply regex replacements to all text files (Tier C)."""
    patterns = []
    for entry in config.get("string_replacements", []):
        patterns.append((re.compile(entry["pattern"]), entry["replacement"]))

    exclude_paths = set(config.get("exclude_paths", []))
    total_replacements = 0

    for root, dirs, files in os.walk(worktree):
        root_path = Path(root)
        rel_root = root_path.relative_to(worktree)

        # Skip directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if any(str(rel_root).startswith(ep.rstrip("/")) for ep in exclude_paths):
            dirs.clear()
            continue

        for fname in files:
            fpath = root_path / fname
            rel_path = fpath.relative_to(worktree)

            # Skip binary files
            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue

            # Skip excluded paths
            if any(str(rel_path).startswith(ep.rstrip("/")) for ep in exclude_paths):
                continue

            # Skip tier-A files (already replaced wholesale)
            tier_a_sources = {e["source"] for e in config.get("file_replacements", [])}
            if str(rel_path) in tier_a_sources:
                continue

            try:
                content = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue

            original = content
            for pattern, replacement in patterns:
                content = pattern.sub(replacement, content)

            if content != original:
                fpath.write_text(content, encoding="utf-8")
                total_replacements += 1

    return total_replacements


def delete_paths(worktree: Path, config: dict) -> int:
    """Delete files that should not be in the public repo."""
    count = 0
    for rel_path in config.get("delete_paths", []):
        target = worktree / rel_path
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            count += 1
            print(f"  deleted: {rel_path}")
    return count


def check_leaks(worktree: Path, config: dict) -> list[str]:
    """Scan for leak markers in the sanitized tree."""
    markers = config.get("leak_markers", [])
    if not markers:
        return []

    violations = []
    exclude_paths = set(config.get("exclude_paths", []))

    for root, dirs, files in os.walk(worktree):
        root_path = Path(root)
        rel_root = root_path.relative_to(worktree)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in files:
            fpath = root_path / fname
            rel_path = fpath.relative_to(worktree)

            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if any(str(rel_path).startswith(ep.rstrip("/")) for ep in exclude_paths):
                continue

            try:
                lines = fpath.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, PermissionError):
                continue

            for i, line in enumerate(lines, 1):
                for marker in markers:
                    if marker in line:
                        violations.append(f"{rel_path}:{i}: contains '{marker}'")

    return violations


def commit_and_push(worktree: Path, source_sha: str, push: bool) -> None:
    """Commit sanitized changes and optionally push."""
    run(["git", "add", "-A"], cwd=worktree)

    # Check if there are changes
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=worktree, capture_output=True
    )
    if result.returncode == 0:
        print("No changes to publish (ServerClaw is up to date).")
        return

    run(
        [
            "git", "commit", "-m",
            f"[publish] Sanitized snapshot from {source_sha[:10]}\n\n"
            f"Source: proxmox_florin_server main @ {source_sha}\n"
            f"Generated by: scripts/publish_to_serverclaw.py\n\n"
            f"Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>",
        ],
        cwd=worktree,
        env={**os.environ, "GIT_COMMITTER_NAME": "ServerClaw Publisher", "GIT_COMMITTER_EMAIL": "noreply@serverclaw.dev"},
    )

    if push:
        # Get the serverclaw remote URL
        result = run(["git", "remote", "get-url", REMOTE_NAME], cwd=REPO_ROOT)
        remote_url = result.stdout.strip()

        run(["git", "remote", "add", REMOTE_NAME, remote_url], cwd=worktree)
        run(["git", "push", "--force", REMOTE_NAME, "HEAD:main"], cwd=worktree)
        print(f"Pushed to {REMOTE_NAME}/main")
    else:
        stat = run(["git", "diff", "--stat", "HEAD~1..HEAD"], cwd=worktree)
        print(f"\nDry-run complete. Changes that would be pushed:\n{stat.stdout}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish sanitized repo to ServerClaw")
    parser.add_argument("--push", action="store_true", help="Actually push to serverclaw remote")
    parser.add_argument("--diff", action="store_true", help="Show diff vs current serverclaw/main")
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found: {CONFIG_PATH}", file=sys.stderr)
        return 1

    config = load_config()

    # Get current source SHA
    source_sha = run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).stdout.strip()
    print(f"Source: main @ {source_sha[:10]}")

    # Create temporary worktree
    print("Creating temporary worktree...")
    worktree = create_worktree()

    try:
        # Tier A: file replacements
        print("\nTier A: File replacements")
        n_replaced = apply_file_replacements(worktree, config)

        # Delete unwanted files
        print("\nDeleting excluded files")
        n_deleted = delete_paths(worktree, config)

        # Tier C: string replacements
        print("\nTier C: String replacements")
        n_sanitized = apply_string_replacements(worktree, config)
        print(f"  sanitized {n_sanitized} files")

        # Leak check
        print("\nLeak check...")
        violations = check_leaks(worktree, config)
        if violations:
            print(f"\nABORT: {len(violations)} leak(s) found:", file=sys.stderr)
            for v in violations[:50]:
                print(f"  {v}", file=sys.stderr)
            if len(violations) > 50:
                print(f"  ... and {len(violations) - 50} more", file=sys.stderr)
            return 1

        print(f"  PASSED (no leaks detected)")
        print(f"\nSummary: {n_replaced} files replaced, {n_deleted} deleted, {n_sanitized} files sanitized")

        # Commit and optionally push
        commit_and_push(worktree, source_sha, push=args.push)

        return 0
    finally:
        print("\nCleaning up worktree...")
        remove_worktree(worktree)


if __name__ == "__main__":
    raise SystemExit(main())
