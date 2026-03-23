#!/usr/bin/env python3
"""HTTP smoke tests for restored docker-runtime guests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any


def _probe_command(url: str, expected_status: int) -> str:
    return (
        "python3 - <<'PY'\n"
        "import sys\n"
        "import urllib.request\n"
        f"url = {url!r}\n"
        f"expected = {expected_status}\n"
        "request = urllib.request.Request(url, method='GET')\n"
        "with urllib.request.urlopen(request, timeout=10) as response:\n"
        "    status = response.status\n"
        "    print(status)\n"
        "    sys.exit(0 if status == expected else 1)\n"
        "PY"
    )


def run_smoke_tests(
    execute_command: Callable[[str], Any],
    *,
    probes: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for probe in probes:
        expected_status = int(probe.get("expected_status", 200))
        command = _probe_command(str(probe["url"]), expected_status)
        outcome = execute_command(command)
        results.append(
            {
                "name": str(probe["name"]),
                "status": "pass" if outcome.returncode == 0 else "fail",
                "required": bool(probe.get("required", True)),
                "url": probe["url"],
                "expected_status": expected_status,
                "stdout": outcome.stdout,
                "stderr": outcome.stderr,
            }
        )
    return results
