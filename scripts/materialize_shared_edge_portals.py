#!/usr/bin/env python3
"""Materialize shared edge portal bundles in isolated worktrees."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_BOOTSTRAP_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_BOOTSTRAP_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_REPO_ROOT))

from platform.repo import REPO_ROOT, shared_repo_root


PORTAL_GENERATORS = {
    "ops-portal": "make generate-ops-portal",
    "changelog-portal": "make generate-changelog-portal",
    "docs-portal": "make docs",
}


def _dir_ready(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def _copy_tree(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _prepare_generation_target(target: Path) -> None:
    if not target.exists():
        return
    if target.is_dir():
        shutil.rmtree(target)
        return
    target.unlink()


def _run(command: str) -> None:
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        shell=True,
        executable="/bin/bash",
        env=os.environ.copy(),
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise RuntimeError(f"`{command}` exited {completed.returncode}: {detail.splitlines()[-1]}")


def materialize() -> None:
    shared_root = shared_repo_root(REPO_ROOT)
    for portal_name, command in PORTAL_GENERATORS.items():
        target = REPO_ROOT / "build" / portal_name
        if _dir_ready(target):
            print(f"ready {target}")
            continue

        shared_target = shared_root / "build" / portal_name
        if shared_root != REPO_ROOT and _dir_ready(shared_target):
            _copy_tree(shared_target, target)
            print(f"copied {shared_target} -> {target}")
            continue

        _prepare_generation_target(target)
        _run(command)
        if not _dir_ready(target):
            raise RuntimeError(f"`{command}` completed but {target} is still missing or empty")
        print(f"generated {target} via `{command}`")


def main() -> int:
    materialize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
