#!/usr/bin/env python3
"""Auto-rewrite workstream `shared_surfaces` paths after file renames — ADR 0450 phase 5.2.

Three of the dangling-surface signals from ws-0447 traceability come
from file renames in agent A's PR leaving agent B's workstream YAML
pointing at a dead path. This script closes that class without
operator intervention.

Operates in two modes:

  --since <ref>     Detect renames between `<ref>...HEAD` via
                    `git diff --diff-filter=R --name-status`. Used by
                    the post-merge git hook (`<ref>` defaults to
                    `ORIG_HEAD`, the pre-merge tip).
  --pairs A:B C:D   Apply explicit (old, new) pairs. Used by tests and
                    operators who know the rename and want to fix the
                    workstream YAMLs in one shot.

For each pair, the script scans `workstreams/active/*.yaml` and
`workstreams/archive/**/*.yaml`, replaces exact-match `<old>` with
`<new>` in every `shared_surfaces:` list entry, and reports the
changes. Default mode is **dry-run** — surfaces what would change
without writing. `--apply` mutates the YAMLs.

The substitution is conservative: exact string match per list entry,
no fuzzy matches, no regex, no path-component edits. This avoids the
"renamed `roles/foo/x` to `roles/bar/x` and accidentally touched
`roles/foo/y`" class of mistake.

Exit codes:

    0  no changes (dry-run or apply)
    0  changes detected (dry-run)
    0  changes applied (--apply)
    1  --apply failed (e.g. YAML parse error mid-write)
    2  invocation error
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSTREAMS_ACTIVE = REPO_ROOT / "workstreams" / "active"
WORKSTREAMS_ARCHIVE = REPO_ROOT / "workstreams" / "archive"


@dataclass(frozen=True)
class Rename:
    old: str
    new: str


@dataclass
class RewriteResult:
    workstream_yaml: str  # repo-relative path
    rename: Rename
    line_number: int  # 1-indexed
    line_before: str
    line_after: str


def parse_renames_from_git_diff(output: str) -> list[Rename]:
    """Parse `git diff --diff-filter=R --name-status` output.

    Each line is `R<score>\t<old>\t<new>`. Whitespace separators may
    be tabs or spaces depending on git config.
    """
    renames: list[Rename] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or not line.upper().startswith("R"):
            continue
        # The first whitespace-separated field is "R<NN>"; ignore it.
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) < 3:
            continue
        old, new = parts[1], parts[2]
        if old and new and old != new:
            renames.append(Rename(old=old, new=new))
    return renames


def detect_renames_via_git(since: str, *, repo_root: Path) -> list[Rename]:
    """Run `git diff --diff-filter=R --name-status <since>...HEAD`.

    Returns an empty list on any git failure (the hook should never
    crash a merge — surfacing zero renames is the safe default).
    """
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "diff",
        "--diff-filter=R",
        "--name-status",
        f"{since}...HEAD",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return parse_renames_from_git_diff(proc.stdout)


# ---------------------------------------------------------------------------
# YAML rewriting
# ---------------------------------------------------------------------------


def _yaml_files(repo_root: Path) -> list[Path]:
    """Return every workstream YAML the rewriter should consider.

    Scans both `workstreams/active/*.yaml` and `workstreams/archive/**/*.yaml`.
    Skips files starting with `_` or `.` (template / hidden).
    """
    out: list[Path] = []
    active = repo_root / "workstreams" / "active"
    archive = repo_root / "workstreams" / "archive"
    if active.is_dir():
        out.extend(p for p in sorted(active.glob("*.yaml")) if not p.name.startswith(("_", ".")))
    if archive.is_dir():
        out.extend(p for p in sorted(archive.rglob("*.yaml")) if not p.name.startswith(("_", ".")))
    return out


def rewrite_one_file(
    path: Path,
    renames: Iterable[Rename],
    *,
    repo_root: Path,
    apply: bool,
) -> list[RewriteResult]:
    """Apply rename substitutions to one YAML file. Returns the changes
    that would be (or were) made. Conservative line-by-line replacement
    keyed on the exact `<old>` token within `shared_surfaces:` list entries.

    The match is anchored to lines starting with `- ` (YAML list-item
    syntax) AND containing the exact `<old>` after the dash. This avoids
    rewriting `summary:` / `notes:` prose that happens to mention the
    old path.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    results: list[RewriteResult] = []
    rename_list = list(renames)
    if not rename_list:
        return results

    in_shared_surfaces = False
    for idx, line in enumerate(lines):
        stripped_left = line.lstrip()
        # Detect shared_surfaces: block opening.
        if stripped_left.startswith("shared_surfaces:"):
            in_shared_surfaces = True
            continue
        # Block ends when we hit a top-level key (no leading space) or
        # a different key at the same depth as `shared_surfaces:`.
        if (
            in_shared_surfaces
            and stripped_left
            and not stripped_left.startswith("-")
            and not stripped_left.startswith("#")
        ):
            in_shared_surfaces = False
        if not in_shared_surfaces:
            continue
        if not stripped_left.startswith("- "):
            continue
        # The list entry's value is everything after the dash + space.
        # Comments (after `#`) are not eligible for rename — only the
        # path portion.
        leading_indent = line[: len(line) - len(stripped_left)]
        body = stripped_left[2:]  # strip "- "
        comment_idx = body.find("#")
        if comment_idx == -1:
            value = body.rstrip("\r\n")
            comment = ""
            trailing_nl = line[len(line) - 1] if line.endswith("\n") else ""
            if line.endswith("\r\n"):
                trailing_nl = "\r\n"
        else:
            value = body[:comment_idx].rstrip()
            comment = body[comment_idx:]
            trailing_nl = "\n" if line.endswith("\n") else ""
            if line.endswith("\r\n"):
                trailing_nl = "\r\n"
        # Strip surrounding quotes if any (rare in workstream YAMLs).
        unquoted = value.strip().strip("\"'")
        for rename in rename_list:
            if unquoted == rename.old:
                new_body = f"- {rename.new}"
                if comment:
                    new_body += f"  {comment.rstrip()}"
                new_line = leading_indent + new_body + (trailing_nl or "\n")
                results.append(
                    RewriteResult(
                        workstream_yaml=str(path.relative_to(repo_root)),
                        rename=rename,
                        line_number=idx + 1,
                        line_before=line.rstrip("\r\n"),
                        line_after=new_line.rstrip("\r\n"),
                    )
                )
                lines[idx] = new_line
                break  # one rename per line; subsequent rename pairs would no-op anyway
    if apply and results:
        path.write_text("".join(lines), encoding="utf-8")
    return results


def rewrite_all(
    renames: Iterable[Rename],
    *,
    repo_root: Path,
    apply: bool,
) -> list[RewriteResult]:
    rename_list = list(renames)
    if not rename_list:
        return []
    results: list[RewriteResult] = []
    for path in _yaml_files(repo_root):
        results.extend(rewrite_one_file(path, rename_list, repo_root=repo_root, apply=apply))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_pair_args(raw: list[str]) -> list[Rename]:
    out: list[Rename] = []
    for item in raw:
        if ":" not in item:
            raise ValueError(f"--pair argument {item!r} must use OLD:NEW format")
        old, new = item.split(":", 1)
        if not old or not new:
            raise ValueError(f"--pair {item!r} has empty side")
        out.append(Rename(old=old, new=new))
    return out


def format_human(results: list[RewriteResult], *, applied: bool) -> str:
    if not results:
        return "heal_workstream_renames: no matching paths in workstream YAMLs."
    lines = []
    verb = "rewrote" if applied else "would rewrite"
    by_file: dict[str, list[RewriteResult]] = {}
    for r in results:
        by_file.setdefault(r.workstream_yaml, []).append(r)
    lines.append(f"heal_workstream_renames: {verb} {len(results)} path(s) across {len(by_file)} workstream(s):")
    for path in sorted(by_file):
        for r in by_file[path]:
            lines.append(f"  {path}:{r.line_number}")
            lines.append(f"    - {r.rename.old}")
            lines.append(f"    + {r.rename.new}")
    if not applied:
        lines.append("\nRe-run with --apply to write the changes.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--since",
        help="Detect renames between <ref>...HEAD via git diff. "
        "Conventional value from a post-merge hook is ORIG_HEAD.",
    )
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        help="Explicit OLD:NEW rename pair. Repeatable. Used for tests and operator-driven runs without git history.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate workstream YAMLs (default: dry-run, report only).",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repo root override (for tests).",
    )
    args = parser.parse_args(argv)

    if not args.since and not args.pair:
        parser.print_help(sys.stderr)
        return 2

    repo_root = Path(args.root)
    renames: list[Rename] = []
    if args.since:
        if not shutil.which("git"):
            print("heal_workstream_renames: git not on PATH", file=sys.stderr)
            return 2
        renames.extend(detect_renames_via_git(args.since, repo_root=repo_root))
    if args.pair:
        try:
            renames.extend(parse_pair_args(args.pair))
        except ValueError as exc:
            print(f"heal_workstream_renames: {exc}", file=sys.stderr)
            return 2

    if not renames:
        print("heal_workstream_renames: no renames detected; nothing to do.")
        return 0

    try:
        results = rewrite_all(renames, repo_root=repo_root, apply=args.apply)
    except OSError as exc:
        print(f"heal_workstream_renames: {exc}", file=sys.stderr)
        return 1
    print(format_human(results, applied=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
