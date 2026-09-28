from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_ad_hoc_retry import IGNORED_PATHS, RetryLoopVisitor  # noqa: E402


def findings_for(source: str) -> list[object]:
    visitor = RetryLoopVisitor(Path("fixture.py"), source_lines=source.splitlines())
    visitor.visit(ast.parse(source))
    return visitor.findings


def test_raw_sleep_in_retry_loop_is_reported() -> None:
    source = "for retry_attempt in range(3):\n    time.sleep(1)\n"

    findings = findings_for(source)

    assert len(findings) == 1
    assert "raw time.sleep" in findings[0].message


def test_documented_retry_guard_exception_is_allowed() -> None:
    source = (
        "# retry-guard: allow: dedicated wrapper records every attempt\n"
        "for retry_attempt in range(3):\n"
        "    time.sleep(1)\n"
    )

    assert findings_for(source) == []


def test_retry_guard_exception_requires_a_reason() -> None:
    source = "# retry-guard: allow:\nfor retry_attempt in range(3):\n    time.sleep(1)\n"

    assert len(findings_for(source)) == 1


def test_receipt_producing_ssh_wrapper_is_explicitly_excluded_from_scan() -> None:
    assert Path("scripts/ssh_with_retry.py") in IGNORED_PATHS
