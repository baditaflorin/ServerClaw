#!/usr/bin/env python3
"""Sanitize the private repo and push to the public ServerClaw repo.

Usage:
    python3 scripts/publish_to_serverclaw.py              # dry-run (sanitize + leak check, no push)
    python3 scripts/publish_to_serverclaw.py --push        # sanitize + push to serverclaw remote
    python3 scripts/publish_to_serverclaw.py --diff        # show what would change vs current serverclaw/main
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

import yaml

from audit_sanitization_coverage import (
    check_coverage,
    derive_leak_markers,
    extract_sensitive_values,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "publication-sanitization.yaml"
REMOTE_NAME = "serverclaw"
PUBLIC_DEFAULT_BRANCH = "main"

# Binary file extensions to skip during regex replacement
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

# Directories to always skip
SKIP_DIRS = frozenset({".git", "__pycache__", ".terraform", "node_modules"})

# These manifests describe captured file bytes, which Tier C may intentionally change.
CAPTURED_FILE_MANIFESTS = ("config/0mcp/docker-build-lv3/files.sha256",)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        print(f"  CMD FAILED: {' '.join(cmd)}", file=sys.stderr)
        if result.stderr:
            print(f"  STDERR: {result.stderr.strip()}", file=sys.stderr)
        result.check_returncode()
    return result


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

            # Skip binary files and .git file (worktree pointer)
            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if fname == ".git":
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


def _export_path_checker(worktree: Path) -> Callable[[Path], Path]:
    """Confine derived-artifact writes to a disposable, non-aliased export."""
    if worktree.is_symlink() or not worktree.is_dir():
        raise ValueError("Public export root must be a directory without a symlink")
    export_root = worktree.resolve(strict=True)
    if export_root.samefile(REPO_ROOT):
        raise ValueError("Public export cannot be the source checkout")

    def checked_export_path(path: Path) -> Path:
        relative = path.relative_to(worktree)
        current = worktree
        for part in relative.parts:
            if part == "..":
                raise ValueError("Captured-file path escapes the public export")
            current = current / part
            if current.is_symlink():
                raise ValueError(f"Captured-file path contains a symlink: {relative}")
        try:
            path.resolve().relative_to(export_root)
        except ValueError as error:
            raise ValueError(f"Captured-file path resolves outside the public export: {relative}") from error
        return path

    return checked_export_path


def refresh_captured_file_manifests(worktree: Path) -> None:
    """Refresh exported hashes while preserving the exact file-set contract."""
    checked_export_path = _export_path_checker(worktree)
    for relative in CAPTURED_FILE_MANIFESTS:
        manifest = worktree / relative
        checked_export_path(manifest)
        if manifest.is_symlink():
            raise ValueError(f"Captured-file manifest cannot be a symlink: {relative}")
        if not manifest.exists():
            continue
        if not manifest.is_file():
            raise ValueError(f"Captured-file manifest must be a regular file: {relative}")
        if manifest.stat().st_nlink != 1:
            raise ValueError(f"Captured-file manifest cannot share a hard link: {relative}")
        files = manifest.parent / "files"
        checked_export_path(files)
        if files.is_symlink() or not files.is_dir():
            raise ValueError(f"Captured files root must be a directory without a symlink: {relative}")
        expected: set[str] = set()
        for line in manifest.read_text(encoding="utf-8").splitlines():
            digest, name = line.split(None, 1)
            name = name.strip()
            path = Path(name)
            if not re.fullmatch(r"[0-9a-f]{64}", digest) or path.is_absolute() or ".." in path.parts or name in expected:
                raise ValueError(f"Invalid captured-file manifest entry in {relative}: {name}")
            expected.add(name)
        actual: set[str] = set()
        for path in files.rglob("*"):
            checked_export_path(path)
            if path.is_symlink():
                raise ValueError(f"Captured-file manifest cannot follow symlinks: {path.relative_to(worktree)}")
            if path.is_file():
                actual.add(path.relative_to(files).as_posix())
        if actual != expected:
            raise ValueError(f"Captured-file manifest file set changed in {relative}")
        checked_export_path(manifest)
        manifest.write_text(
            "".join(f"{hashlib.sha256((files / name).read_bytes()).hexdigest()}  {name}\n" for name in sorted(expected)),
            encoding="utf-8",
        )


def refresh_network_policy_baselines(worktree: Path) -> None:
    """Remove only accepted findings eliminated by the public projection.

    New findings always abort publication. Every policy is checked before any
    baseline is written; private operational baselines are never passed here.
    """
    import netpolicy

    checked_export_path = _export_path_checker(worktree)
    directory = checked_export_path(worktree / "config" / "network-policy")
    if not directory.exists():
        return
    if not directory.is_dir():
        raise ValueError("Public network-policy root must be a directory")
    policies = sorted(directory.glob("*.yaml"))
    expected_baselines = {path.with_suffix(".baseline.json") for path in policies}
    if set(directory.glob("*.baseline.json")) != expected_baselines:
        raise ValueError("Public network policies and baselines must be paired")
    updates: list[tuple[Path, list[str]]] = []
    for policy_path in policies:
        checked_export_path(policy_path)
        if not policy_path.is_file() or policy_path.stat().st_nlink != 1:
            raise ValueError(f"Public network policy must be a regular unshared file: {policy_path.name}")
        baseline = checked_export_path(policy_path.with_suffix(".baseline.json"))
        if not baseline.is_file() or baseline.stat().st_nlink != 1:
            raise ValueError(f"Public network baseline must be a regular unshared file: {baseline.name}")
        accepted = json.loads(baseline.read_text(encoding="utf-8"))
        if not isinstance(accepted, list) or not all(isinstance(item, str) for item in accepted) or len(set(accepted)) != len(accepted):
            raise ValueError(f"Invalid public network baseline: {baseline.name}")
        findings = {finding["id"] for finding in netpolicy.check(netpolicy.load_policy(policy_path))
                    if finding["severity"] != "info"}
        if findings - set(accepted):
            raise ValueError(f"Public network policy introduces unaccepted findings: {policy_path.name}")
        retained = [item for item in accepted if item in findings]
        if retained != accepted:
            updates.append((baseline, retained))
    for baseline, retained in updates:
        checked_export_path(baseline)
        if not baseline.is_file() or baseline.stat().st_nlink != 1:
            raise ValueError(f"Public network baseline changed file identity: {baseline.name}")
        baseline.write_text(json.dumps(retained, indent=1) + "\n", encoding="utf-8")


def regenerate_public_derived_artifacts(worktree: Path) -> None:
    """Regenerate committed derived files after Tier A source replacements.

    The public host and identity templates intentionally differ from the
    private deployment inputs.  Their generated inventory must therefore be
    rebuilt before the snapshot is committed, otherwise ServerClaw CI detects
    stale generated files immediately after `make generate-platform-vars`.
    """
    refresh_network_policy_baselines(worktree)
    run(["make", "generate-platform-vars"], cwd=worktree)
    # `generate-platform-vars` first refreshes cross-cutting artifacts, then
    # embeds them in platform.yml. A second pass establishes that generated
    # fixed point after Tier A inputs change together.
    run(["make", "generate-platform-vars"], cwd=worktree)
    # A captured config can contain a private hostname or network. Its public
    # replacement must have a checksum of the exported bytes, not the private input.
    refresh_captured_file_manifests(worktree)


def check_leaks(worktree: Path, config: dict) -> list[str]:
    """Scan for leak markers in the sanitized tree.

    Deliberately does NOT skip config["exclude_paths"] here. exclude_paths only
    means "don't run Tier C regex rewriting on this path" (e.g. because its
    content is already generic by design, like publication/templates/) -- it
    is not a statement that the path is safe to skip for leak detection too.
    Conflating the two let a real PII leak (scripts/one-time/adr-0409-*.py,
    which is exempt from rewriting specifically because it documents real
    values) through undetected on 2026-08-26. delete_paths entries are fine
    to not special-case here since delete_paths() already runs before this
    and physically removes them from the worktree.
    """
    markers = config.get("leak_markers", [])
    if not markers:
        return []

    violations = []

    for root, dirs, files in os.walk(worktree):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for fname in files:
            fpath = root_path / fname
            rel_path = fpath.relative_to(worktree)

            if fpath.suffix.lower() in BINARY_EXTENSIONS:
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


def base_branch_snapshot_on_public_main(worktree: Path) -> None:
    """Make the staged sanitized tree a clean descendant of ServerClaw main.

    A publish branch is a complete snapshot, so its original parent is the
    private repository's commit.  Resetting only HEAD after staging preserves
    that snapshot tree while making its eventual public PR merge cleanly
    against the current protected ServerClaw default branch.
    """
    run(["git", "fetch", REMOTE_NAME, PUBLIC_DEFAULT_BRANCH], cwd=worktree)
    run(["git", "reset", "--soft", f"{REMOTE_NAME}/{PUBLIC_DEFAULT_BRANCH}"], cwd=worktree)


def commit_and_push(worktree: Path, source_sha: str, push: bool, branch: str | None = None) -> None:
    """Commit sanitized changes and optionally push."""
    run(["git", "add", "-A"], cwd=worktree)

    # ServerClaw main is protected. For a publish branch, build a commit with
    # the exact sanitized snapshot tree but the live public main as its parent,
    # so unrelated public updates do not make the publication PR conflict.
    if branch:
        base_branch_snapshot_on_public_main(worktree)

    # Check if there are changes
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=worktree, capture_output=True)
    if result.returncode == 0:
        print("No changes to publish (ServerClaw is up to date).")
        return

    # Skip pre-commit hooks — the worktree is a sanitized snapshot, not a development commit.
    # Hooks would fail on formatting differences introduced by the string replacements.
    run(
        [
            "git",
            "commit",
            "--no-verify",
            "-m",
            f"[publish] Sanitized snapshot from {source_sha[:10]}\n\n"
            f"Source: platform_server main @ {source_sha}\n"
            f"Generated by: scripts/publish_to_serverclaw.py\n\n"
            f"Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>",
        ],
        cwd=worktree,
        env={
            **os.environ,
            "GIT_COMMITTER_NAME": "ServerClaw Publisher",
            "GIT_COMMITTER_EMAIL": "noreply@serverclaw.dev",
        },
    )

    if push:
        # The worktree shares remotes with the parent repo, so just push directly.
        # Skip pre-push hooks — the sanitized worktree may not pass the
        # validation gate (changed domains, IPs, etc.)
        run(["git", "remote", "get-url", REMOTE_NAME], cwd=worktree)
        target_ref = f"HEAD:refs/heads/{branch}" if branch else "HEAD:main"
        run(
            ["git", "push", "--force", "--no-verify", REMOTE_NAME, target_ref],
            cwd=worktree,
        )
        print(f"Pushed to {REMOTE_NAME}/{branch or 'main'}")
    else:
        stat = run(["git", "diff", "--stat", "HEAD~1..HEAD"], cwd=worktree)
        print(f"\nDry-run complete. Changes that would be pushed:\n{stat.stdout}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish sanitized repo to ServerClaw")
    parser.add_argument("--push", action="store_true", help="Actually push to serverclaw remote")
    parser.add_argument("--diff", action="store_true", help="Show diff vs current serverclaw/main")
    parser.add_argument(
        "--branch",
        help=(
            "Push to this branch instead of force-pushing main directly. Required now that "
            "ServerClaw's main has a required-status-check ruleset (ci/woodpecker/push/woodpecker) "
            "-- a direct force-push can never satisfy that (the check can't exist for content "
            "that hasn't landed yet). Push a branch, let Woodpecker run, merge via PR instead."
        ),
    )
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        print(f"ERROR: Config not found: {CONFIG_PATH}", file=sys.stderr)
        return 1

    config = load_config()

    # Pre-publish coverage audit
    print("Pre-publish coverage audit...")
    values = extract_sensitive_values()
    _covered, gaps = check_coverage(values, config)
    critical = [g for g in gaps if g.severity == "CRITICAL"]
    warnings = [g for g in gaps if g.severity == "WARNING"]
    if critical:
        print(f"\nABORT: {len(critical)} CRITICAL coverage gap(s):", file=sys.stderr)
        for g in critical:
            print(f"  {g.value}  ({g.category}, from {g.source})", file=sys.stderr)
        print("\nFix config/publication-sanitization.yaml or run:", file=sys.stderr)
        print("  python3 scripts/audit_sanitization_coverage.py", file=sys.stderr)
        return 1
    if warnings:
        print(f"  {len(warnings)} WARNING gap(s) — deployment names without patterns")
        for g in warnings:
            print(f"    {g.value}  (from {g.source})")

    # Merge auto-derived leak markers with manual ones
    auto_markers = derive_leak_markers(values)
    manual_markers = config.get("leak_markers", [])
    config["leak_markers"] = sorted(set(auto_markers) | set(manual_markers))
    print(
        f"  Leak markers: {len(config['leak_markers'])} ({len(auto_markers)} auto + {len(manual_markers)} manual, {len(config['leak_markers'])} unique)"
    )

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

        # Tier A templates replace generator inputs wholesale. Rebuild the
        # committed generated files before validating or publishing the fork.
        print("\nRegenerating public derived artifacts")
        regenerate_public_derived_artifacts(worktree)

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

        print("  PASSED (no leaks detected)")
        print(f"\nSummary: {n_replaced} files replaced, {n_deleted} deleted, {n_sanitized} files sanitized")

        # Commit and optionally push
        commit_and_push(worktree, source_sha, push=args.push, branch=args.branch)

        return 0
    finally:
        print("\nCleaning up worktree...")
        remove_worktree(worktree)


if __name__ == "__main__":
    raise SystemExit(main())
