#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("platform", "scripts")
IGNORED_PATHS = {
    Path("platform/retry/classification.py"),
    Path("platform/retry/policy.py"),
}
RETRY_TOKENS = ("attempt", "retry", "retries", "backoff", "max_attempts", "retry_delay")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str


class RetryLoopVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[Finding] = []

    def visit_For(self, node: ast.For) -> None:
        self._check_loop(node)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._check_loop(node)
        self.generic_visit(node)

    def _check_loop(self, node: ast.For | ast.While) -> None:
        if not self._looks_retry_related(node):
            return
        if any(self._is_time_sleep(call) for call in ast.walk(node) if isinstance(call, ast.Call)):
            self.findings.append(
                Finding(
                    path=self.path,
                    line=node.lineno,
                    message="retry-like loop uses raw time.sleep; migrate to platform.retry.with_retry",
                )
            )

    @staticmethod
    def _is_time_sleep(node: ast.Call) -> bool:
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "time"
            and func.attr == "sleep"
        )

    @staticmethod
    def _looks_retry_related(node: ast.For | ast.While) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and any(token in child.id.lower() for token in RETRY_TOKENS):
                return True
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                lowered = child.value.lower()
                if any(token in lowered for token in RETRY_TOKENS):
                    return True
        return False


def iter_python_paths() -> list[Path]:
    paths: list[Path] = []
    for root in SCAN_ROOTS:
        for path in (REPO_ROOT / root).rglob("*.py"):
            relative = path.relative_to(REPO_ROOT)
            if relative in IGNORED_PATHS:
                continue
            paths.append(path)
    return sorted(paths)


def collect_findings() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_python_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = RetryLoopVisitor(path.relative_to(REPO_ROOT))
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard against ad hoc retry loops outside platform.retry.")
    parser.parse_args()
    findings = collect_findings()
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.message}")
        return 1
    print("Ad hoc retry guard OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
