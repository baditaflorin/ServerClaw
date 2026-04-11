#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path

from controller_automation_toolkit import emit_cli_error, repo_path


DEFAULT_TARGETS = (
    "platform/scheduler",
    "platform/world_state/workers.py",
    "scripts/api_gateway/main.py",
    "scripts/drift_lib.py",
    "scripts/netbox_inventory_sync.py",
    "windmill/scheduler/watchdog-loop.py",
    "config/windmill/scripts/scheduler-watchdog-loop.py",
)

TIMEOUT_PATTERN = re.compile(r"\btimeout\s*=\s*[0-9]")
SSH_PATTERN = re.compile(r"ConnectTimeout=\d")


def iter_paths(targets: list[str]) -> list[Path]:
    root = repo_path()
    resolved: list[Path] = []
    for target in targets:
        path = root / target
        if path.is_dir():
            resolved.extend(sorted(child for child in path.rglob("*.py") if child.is_file()))
            continue
        resolved.append(path)
    return resolved


def scan(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    root = repo_path()
    for path in paths:
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if TIMEOUT_PATTERN.search(line) or SSH_PATTERN.search(line):
                violations.append(f"{path.relative_to(root)}:{line_number}: {line.strip()}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when targeted source files still contain hardcoded timeout literals."
    )
    parser.add_argument("targets", nargs="*", default=list(DEFAULT_TARGETS))
    args = parser.parse_args()

    try:
        violations = scan(iter_paths(list(args.targets)))
    except OSError as exc:
        return emit_cli_error("Hardcoded timeout scan", exc)

    if violations:
        return emit_cli_error(
            "Hardcoded timeout scan",
            RuntimeError("hardcoded timeout literals remain:\n" + "\n".join(violations)),
        )
    print("Hardcoded timeout scan OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
