#!/usr/bin/env python3
"""Per-service convergence dry-run helper — ADR 0444 item 10.

Pre-merge guard that catches the class of bugs the 0fork bootstrap loop
discovered the hard way (releases 0.178.222 → 0.179.4): a role works
against the lv3 deployment because of a hardcoded `lv3_*` literal but
fails the moment a different identity overlay is loaded.

This script:

1. Detects roles changed since a base ref via `git diff` (default
   `origin/main...HEAD`).
2. For each changed role, finds the playbook(s) that include it.
3. Runs `ansible-playbook --syntax-check` against each fixture overlay
   under `tests/fixtures/inventories/` — fast (no SSH, no inventory
   resolution beyond the playbook itself), suitable for a pre-push gate.
4. Reports a (role × fixture) pass/fail matrix.

A `--mode full` flag runs the heavier `--check --diff` per cell, useful
for manual investigation but too slow for the gate.

Two design notes:

- The script does not depend on Ansible being importable as a Python
  module — it shells out to `ansible-playbook`. That keeps the test
  suite light: tests cover the helper functions directly, no Ansible
  install required.
- A role can be referenced by either short name (e.g. `authentik_runtime`)
  or fully-qualified name (`lv3.platform.authentik_runtime`). The
  discovery routine accepts both. ADR 0438 keeps the flat `roles/` tree
  mirrored to `collections/.../roles/`, so a role usually exists under
  both paths.

Exit status:

  0 — every (changed-role × fixture) cell passed (or no roles changed)
  1 — at least one cell failed
  2 — invocation error (missing fixtures, bad CLI args, etc.)

The pre-push gate wires this in advisory mode initially; ADR 0444 phase 5
promotes it to required.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "inventories"
ROLE_PATHS = (
    REPO_ROOT / "roles",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles",
)
PLAYBOOK_DIRS = (
    REPO_ROOT / "playbooks",
    REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "playbooks",
)


@dataclass(frozen=True)
class CellResult:
    """One (role × fixture) cell of the dry-run matrix."""

    role: str
    fixture: str
    playbook: str
    passed: bool
    detail: str  # short failure summary or "ok"


# ---------------------------------------------------------------------------
# Changed-role detection
# ---------------------------------------------------------------------------


def detect_changed_roles(base_ref: str, head_ref: str = "HEAD") -> list[str]:
    """Return role names whose files changed between base_ref and head_ref.

    Uses `git diff --name-only` and matches files under any path in
    ROLE_PATHS. The role name is the first directory component after the
    role-root prefix.
    """
    cmd = ["git", "-C", str(REPO_ROOT), "diff", "--name-only", f"{base_ref}...{head_ref}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    return _extract_role_names(proc.stdout.splitlines())


def _extract_role_names(changed_files: Iterable[str]) -> list[str]:
    role_root_prefixes = tuple(str(p.relative_to(REPO_ROOT)).rstrip("/") + "/" for p in ROLE_PATHS)
    seen: set[str] = set()
    for line in changed_files:
        line = line.strip()
        if not line:
            continue
        for prefix in role_root_prefixes:
            if line.startswith(prefix):
                rest = line[len(prefix) :]
                role_name = rest.split("/", 1)[0]
                if role_name and role_name != "_template":
                    seen.add(role_name)
                break
    return sorted(seen)


# ---------------------------------------------------------------------------
# Playbook discovery
# ---------------------------------------------------------------------------


# Two narrow patterns to avoid false positives like `- name: foo`:
#   - `role: <name>` or `role: lv3.platform.<name>`
#   - any standalone `lv3.platform.<name>` reference
_ROLE_REF_PATTERNS = (
    re.compile(r"\brole:\s*(?:lv3\.platform\.)?([a-z][a-z0-9_]*)\b"),
    re.compile(r"\blv3\.platform\.([a-z][a-z0-9_]*)\b"),
)


def find_playbooks_for_role(role: str) -> list[Path]:
    """Return playbook paths that reference `role` by short or FQ name."""
    matches: list[Path] = []
    for pb_dir in PLAYBOOK_DIRS:
        if not pb_dir.is_dir():
            continue
        for path in sorted(pb_dir.glob("*.yml")):
            text = _read_text_safe(path)
            if not text:
                continue
            referenced = _roles_referenced(text)
            if role in referenced:
                matches.append(path)
    return matches


def _read_text_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _roles_referenced(playbook_text: str) -> set[str]:
    refs: set[str] = set()
    for pattern in _ROLE_REF_PATTERNS:
        for match in pattern.finditer(playbook_text):
            refs.add(match.group(1))
    return refs


# ---------------------------------------------------------------------------
# Fixture discovery
# ---------------------------------------------------------------------------


def discover_fixtures(selector: str = "all") -> list[Path]:
    """Return the fixture overlay files to exercise.

    `selector` is "all" or a comma-separated list of fixture stems
    (`lv3`, `0fork`, `synthetic`, …). Stems map to `<stem>-shape.yml`
    under FIXTURE_DIR.
    """
    if not FIXTURE_DIR.is_dir():
        raise RuntimeError(f"fixture directory missing: {FIXTURE_DIR}")
    available = {p.stem.removesuffix("-shape"): p for p in FIXTURE_DIR.glob("*-shape.yml")}
    if not available:
        raise RuntimeError(f"no *-shape.yml fixtures under {FIXTURE_DIR}")
    if selector == "all":
        return [available[k] for k in sorted(available)]
    requested = [s.strip() for s in selector.split(",") if s.strip()]
    missing = [s for s in requested if s not in available]
    if missing:
        raise RuntimeError(f"unknown fixture(s): {missing}; available: {sorted(available)}")
    return [available[s] for s in requested]


# ---------------------------------------------------------------------------
# Cell execution
# ---------------------------------------------------------------------------


def run_cell(
    role: str,
    fixture: Path,
    playbook: Path,
    mode: str,
    *,
    runner: str = "ansible-playbook",
    timeout_seconds: int = 60,
) -> CellResult:
    """Execute one (role × fixture) cell. Returns a CellResult.

    `mode` is "syntax" (default, fast) or "full" (--check --diff, slow).
    """
    cmd = [runner, str(playbook), "--extra-vars", f"@{fixture}"]
    if mode == "syntax":
        cmd.append("--syntax-check")
    elif mode == "full":
        cmd.extend(["--check", "--diff"])
    else:
        raise ValueError(f"unknown mode: {mode!r}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            cwd=REPO_ROOT,
        )
    except subprocess.TimeoutExpired:
        return CellResult(
            role=role,
            fixture=fixture.name,
            playbook=str(playbook.relative_to(REPO_ROOT)),
            passed=False,
            detail=f"timed out after {timeout_seconds}s",
        )
    if proc.returncode == 0:
        return CellResult(
            role=role,
            fixture=fixture.name,
            playbook=str(playbook.relative_to(REPO_ROOT)),
            passed=True,
            detail="ok",
        )
    detail = proc.stderr.strip() or proc.stdout.strip() or "non-zero exit"
    # Trim noisy multi-line ansible output to one short line for the matrix.
    detail = detail.splitlines()[-1][:200]
    return CellResult(
        role=role,
        fixture=fixture.name,
        playbook=str(playbook.relative_to(REPO_ROOT)),
        passed=False,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_matrix(results: list[CellResult]) -> str:
    if not results:
        return "(no cells executed)"
    by_role: dict[str, list[CellResult]] = {}
    for r in results:
        by_role.setdefault(r.role, []).append(r)
    lines = []
    for role in sorted(by_role):
        for cell in by_role[role]:
            mark = "PASS" if cell.passed else "FAIL"
            lines.append(f"  [{mark}] {role:<32} fixture={cell.fixture:<22} playbook={cell.playbook}")
            if not cell.passed:
                lines.append(f"         └─ {cell.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--base",
        default=os.environ.get("CONVERGE_DRY_RUN_BASE", "origin/main"),
        help="base git ref for change detection (default: origin/main)",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="head git ref (default: HEAD)",
    )
    parser.add_argument(
        "--fixtures",
        default="all",
        help='fixtures to run against — "all" or comma-separated stems (default: all)',
    )
    parser.add_argument(
        "--mode",
        choices=("syntax", "full"),
        default="syntax",
        help="syntax = ansible-playbook --syntax-check (fast); full = --check --diff (slow, manual)",
    )
    parser.add_argument(
        "--roles",
        default=None,
        help="comma-separated role names — overrides change detection",
    )
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="exit 0 even on cell failures (for advisory pre-push wiring)",
    )
    args = parser.parse_args(argv)

    try:
        fixtures = discover_fixtures(args.fixtures)
    except RuntimeError as exc:
        print(f"converge_dry_run: {exc}", file=sys.stderr)
        return 2

    if args.roles:
        roles = sorted({r.strip() for r in args.roles.split(",") if r.strip()})
    else:
        try:
            roles = detect_changed_roles(args.base, args.head)
        except RuntimeError as exc:
            print(f"converge_dry_run: {exc}", file=sys.stderr)
            return 2

    if not roles:
        print("converge_dry_run: no changed roles detected — nothing to do.")
        return 0

    if not shutil.which("ansible-playbook"):
        print(
            "converge_dry_run: ansible-playbook not on PATH; cannot run dry-run.",
            file=sys.stderr,
        )
        return 2

    print(f"converge_dry_run: {len(roles)} changed role(s) × {len(fixtures)} fixture(s) ({args.mode} mode)")
    results: list[CellResult] = []
    for role in roles:
        playbooks = find_playbooks_for_role(role)
        if not playbooks:
            results.append(
                CellResult(
                    role=role,
                    fixture="-",
                    playbook="-",
                    passed=False,
                    detail="no playbook references this role",
                )
            )
            continue
        # Use the first playbook that references the role; the matrix
        # value comes from running it against every fixture, not from
        # running every playbook.
        playbook = playbooks[0]
        for fixture in fixtures:
            results.append(run_cell(role, fixture, playbook, args.mode))

    print(_format_matrix(results))
    failed = [r for r in results if not r.passed]
    print(f"converge_dry_run: {len(results) - len(failed)}/{len(results)} cells passed")
    if failed and not args.advisory:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
