#!/usr/bin/env python3
"""Smoke tests for restored backup VM instances."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


def run_smoke_tests(
    execute_command: Callable[[str], Any],
    *,
    commands: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in commands:
        outcome = execute_command(str(command["command"]))
        results.append(
            {
                "name": str(command["name"]),
                "status": "pass" if outcome.returncode == 0 else "fail",
                "required": bool(command.get("required", True)),
                "stdout": outcome.stdout,
                "stderr": outcome.stderr,
            }
        )
    return results
